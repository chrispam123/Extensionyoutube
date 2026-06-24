# -*- coding: utf-8 -*-
"""
Project: Nocturne Backend
Component: Worker Lambda
Purpose: Process YouTube subscriptions and accumulate results in S3.
"""

import json
import os
import boto3
import binascii
import datetime
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger, Tracer

# Capa Shared
from shared.security import decrypt_token
from shared.google_auth import refresh_access_token
from shared.youtube_client import YouTubeClient
from shared.exceptions import QuotaExceededError

logger = Logger()
tracer = Tracer()

# 1. Inicialización de Clientes (Warm Start)
RAW_ENDPOINT = os.getenv("AWS_ENDPOINT_URL")
ENDPOINT_URL = RAW_ENDPOINT if RAW_ENDPOINT and RAW_ENDPOINT.strip() else None

s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL)
dynamo = boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL)
kms_client = boto3.client("kms", endpoint_url=ENDPOINT_URL)
ssm = boto3.client("ssm", endpoint_url=ENDPOINT_URL)
sqs = boto3.client("sqs", endpoint_url=ENDPOINT_URL)


def get_google_secrets():
    """Recupera secretos de SSM con caché en memoria."""
    # Nota: En un entorno real usaríamos una variable global para caché
    cid = ssm.get_parameter(Name="/extension/google/client_id", WithDecryption=True)[
        "Parameter"
    ]["Value"]
    csec = ssm.get_parameter(
        Name="/extension/google/client_secret", WithDecryption=True
    )["Parameter"]["Value"]
    return cid, csec


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    table = dynamo.Table(os.getenv("DYNAMODB_TABLE"))
    queue_url = os.getenv("SQS_QUEUE_URL")
    bucket_name = os.getenv("S3_BUCKET")

    for record in event.get("Records", []):
        try:
            # A. PARSEO DEL MENSAJE
            payload = json.loads(record["body"])
            job_id = payload.get("jobId")
            user_id = payload.get("userId")

            job_key = {"PK": f"USER#{user_id}", "SK": f"JOB#{job_id}"}
            profile_key = {"PK": f"USER#{user_id}", "SK": "PROFILE"}

            logger.info(f"🚀 Procesando relevo para Job: {job_id}")

            # B. RECUPERAR IDENTIDAD Y ESTADO
            profile_item = table.get_item(Key=profile_key).get("Item", {})
            job_item = table.get_item(Key=job_key).get("Item", {})

            if not profile_item or not job_item:
                logger.error("❌ Perfil o Job no encontrado. Abortando.")
                continue

            encrypted_token = profile_item.get("encryptedRefreshToken")
            current_page_token = job_item.get("nextPageToken")
            job_type = job_item.get("type", "EXPORT")

            # C. AUTENTICACIÓN
            client_id, client_secret = get_google_secrets()
            refresh_token = decrypt_token(kms_client, encrypted_token)
            access_token = refresh_access_token(client_id, client_secret, refresh_token)

            # D. EJECUCIÓN Y COSECHA
            yt = YouTubeClient(access_token)
            new_items = []

            if job_type == "EXPORT":
                logger.info("📤 Consultando YouTube API...")
                yt_res = yt.get_subscriptions(
                    max_results=50, page_token=current_page_token
                )
                # Extraemos solo lo que nos interesa para ahorrar espacio
                for item in yt_res.get("items", []):
                    snippet = item.get("snippet", {})
                    new_items.append(
                        {
                            "id": item.get("id"),
                            "title": snippet.get("title"),
                            "channelId": snippet.get("resourceId", {}).get("channelId"),
                            "thumbnail": snippet.get("thumbnails", {})
                            .get("default", {})
                            .get("url"),
                        }
                    )
                next_page_token = yt_res.get("nextPageToken")
            else:
                # Lógica de IMPORT (pendiente de implementar en detalle)
                next_page_token = None

            # =================================================================
            # E. ACUMULACIÓN EN S3 (EL CORAZÓN DE LA ÉPICA)
            # =================================================================
            s3_key = f"exports/{user_id}/{job_id}.json"
            accumulated_data = []

            try:
                # Intentamos descargar lo que ya llevamos cosechado
                existing_obj = s3.get_object(Bucket=bucket_name, Key=s3_key)
                accumulated_data = json.loads(
                    existing_obj["Body"].read().decode("utf-8")
                )
                logger.info(
                    f"📚 Archivo existente recuperado. Canales previos: {len(accumulated_data)}"
                )
            except ClientError as e:
                if e.response["Error"]["Code"] == "NoSuchKey":
                    logger.info("🆕 No hay archivo previo. Iniciando nueva cosecha.")
                else:
                    raise

            # Unimos lo viejo con lo nuevo
            accumulated_data.extend(new_items)

            # Subimos la cosecha actualizada
            s3.put_object(
                Bucket=bucket_name,
                Key=s3_key,
                Body=json.dumps(accumulated_data),
                ContentType="application/json",
            )
            logger.info(
                f"💾 Cosecha guardada en S3. Total actual: {len(accumulated_data)}"
            )

            # =================================================================
            # F. ACTUALIZACIÓN DE PROGRESO Y RELEVO
            # =================================================================
            table.update_item(
                Key=job_key,
                UpdateExpression="SET #s = :run, nextPageToken = :next, updatedAt = :now ADD doneCount :inc",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":run": "RUNNING",
                    ":next": next_page_token,
                    ":inc": len(new_items),
                    ":now": datetime.datetime.now(datetime.UTC).isoformat(),
                },
            )

            if next_page_token:
                sqs.send_message(
                    QueueUrl=queue_url,
                    MessageBody=json.dumps({"jobId": job_id, "userId": user_id}),
                )
            else:
                logger.info(f"🏁 Exportación finalizada. Total: {len(accumulated_data)}")
                table.update_item(
                    Key=job_key,
                    UpdateExpression="SET #s = :done, updatedAt = :now",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={
                        ":done": "DONE",
                        ":now": datetime.datetime.now(datetime.UTC).isoformat(),
                    },
                )

        except QuotaExceededError:
            table.update_item(
                Key=job_key,
                UpdateExpression="SET #s = :paused, updatedAt = :now",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":paused": "PAUSED_QUOTA",
                    ":now": datetime.datetime.now(datetime.UTC).isoformat(),
                },
            )
            return {"status": "paused"}

        except Exception as e:
            logger.exception("🔥 Fallo crítico en el Worker")
            raise e

    return {"status": "processed"}
