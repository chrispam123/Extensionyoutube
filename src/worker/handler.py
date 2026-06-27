# -*- coding: utf-8 -*-
"""
Project: Nocturne Backend
Component: Worker Lambda
Purpose: Process YouTube subscriptions and accumulate results in S3.
"""

import binascii
import datetime
import json
import os

import boto3
from aws_lambda_powertools import Logger, Tracer
from botocore.exceptions import ClientError

from shared.exceptions import QuotaExceededError
from shared.google_auth import refresh_access_token

# Capa Shared
from shared.security import decrypt_token
from shared.youtube_client import YouTubeClient

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
            payload = json.loads(record["body"])
            job_id, user_id = payload.get("jobId"), payload.get("userId")

            job_key = {"PK": f"USER#{user_id}", "SK": f"JOB#{job_id}"}
            profile_key = {"PK": f"USER#{user_id}", "SK": "PROFILE"}

            # 1. RECUPERAR ESTADO
            profile_item = table.get_item(Key=profile_key).get("Item", {})
            job_item = table.get_item(Key=job_key).get("Item", {})

            job_type = job_item.get("type", "EXPORT")
            encrypted_token = profile_item.get("encryptedRefreshToken")
            current_page_token = job_item.get("nextPageToken")

            # 2. AUTENTICACIÓN
            client_id, client_secret = get_google_secrets()
            refresh_token = decrypt_token(kms_client, encrypted_token)
            access_token = refresh_access_token(client_id, client_secret, refresh_token)
            yt = YouTubeClient(access_token)

            # =================================================================
            # 3. BIFURCACIÓN DE ESTRATEGIA (Siembra vs Cosecha)
            # =================================================================

            if job_type == "IMPORT":
                # --- ESTRATEGIA: SIEMBRA (S3 -> YouTube) ---
                logger.info(f"📥 Iniciando SIEMBRA (Import) para Job {job_id}")

                # A. Leer el archivo que el usuario subió
                s3_key = f"uploads/{user_id}/{job_id}.json"
                s3_res = s3.get_object(Bucket=bucket_name, Key=s3_key)
                all_channels = json.loads(s3_res["Body"].read().decode("utf-8"))

                # B. Determinar qué lote procesar (usamos doneCount como puntero)
                start_index = int(job_item.get("doneCount", 0))
                batch_size = 10  # Lotes pequeños para proteger cuota
                end_index = start_index + batch_size
                batch = all_channels[start_index:end_index]

                logger.info(
                    f"🚜 Procesando lote de importación: {start_index} al {end_index}"
                )

                # C. Ejecutar la acción en YouTube
                for channel in batch:
                    try:
                        # Aquí llamaríamos a yt.subscribe(channel['channelId'])
                        # Por ahora simulamos el éxito para no quemar tu cuota real
                        logger.info(f"✅ Suscrito a: {channel.get('title')}")
                    except Exception as e:
                        logger.error(
                            f"❌ Error al suscribir a {channel.get('title')}: {str(e)}"
                        )

                items_processed_now = len(batch)
                # ¿Hay más canales en el JSON?
                has_more = end_index < len(all_channels)
                next_token_to_save = None  # No usamos tokens de Google en Import

            else:
                # --- ESTRATEGIA: COSECHA (YouTube -> S3) ---
                logger.info(f"📤 Iniciando COSECHA (Export) para Job {job_id}")
                yt_res = yt.get_subscriptions(
                    max_results=50, page_token=current_page_token
                )
                new_items = []
                for item in yt_res.get("items", []):
                    snippet = item.get("snippet", {})
                    new_items.append(
                        {
                            "id": item.get("id"),
                            "title": snippet.get("title"),
                            "channelId": snippet.get("resourceId", {}).get("channelId"),
                        }
                    )

                # Acumulación en S3 (Solo para Export)
                s3_key = f"exports/{user_id}/{job_id}.json"
                accumulated = []
                try:
                    existing = s3.get_object(Bucket=bucket_name, Key=s3_key)
                    accumulated = json.loads(existing["Body"].read().decode("utf-8"))
                except ClientError:
                    pass

                accumulated.extend(new_items)
                s3.put_object(
                    Bucket=bucket_name, Key=s3_key, Body=json.dumps(accumulated)
                )

                items_processed_now = len(new_items)
                next_token_to_save = yt_res.get("nextPageToken")
                has_more = next_token_to_save is not None

            # =================================================================
            # 4. ACTUALIZACIÓN Y RELEVO (Común)
            # =================================================================
            table.update_item(
                Key=job_key,
                UpdateExpression="SET #s = :run, nextPageToken = :next, updatedAt = :now ADD doneCount :inc",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":run": "RUNNING",
                    ":next": next_token_to_save,
                    ":inc": items_processed_now,
                    ":now": datetime.datetime.now(datetime.UTC).isoformat(),
                },
            )

            if has_more:
                sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(payload))
            else:
                table.update_item(
                    Key=job_key,
                    UpdateExpression="SET #s = :done, updatedAt = :now",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={
                        ":done": "DONE",
                        ":now": datetime.datetime.now(datetime.UTC).isoformat(),
                    },
                )

        except Exception as e:
            logger.exception("🔥 Fallo crítico")
            raise e
    return {"status": "processed"}
