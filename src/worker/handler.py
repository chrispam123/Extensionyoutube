# -*- coding: utf-8 -*-
"""
Project: Nocturne Backend
Component: Worker Lambda (YouTube Integration + Single Table Design)
"""

import binascii
import datetime
import json
import os

import boto3
from aws_lambda_powertools import Logger, Tracer
from shared.exceptions import InvalidTokenError, QuotaExceededError
from shared.google_auth import refresh_access_token

# Capa Shared
from shared.security import decrypt_token
from shared.youtube_client import YouTubeClient

logger = Logger()
tracer = Tracer()

# Inicialización de Clientes (Warm Start)
RAW_ENDPOINT = os.getenv("AWS_ENDPOINT_URL")
ENDPOINT_URL = RAW_ENDPOINT if RAW_ENDPOINT and RAW_ENDPOINT.strip() else None

s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL)
dynamo = boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL)
kms_client = boto3.client("kms", endpoint_url=ENDPOINT_URL)
ssm = boto3.client("ssm", endpoint_url=ENDPOINT_URL)
sqs = boto3.client("sqs", endpoint_url=ENDPOINT_URL)


def get_google_secrets():
    if not os.getenv("AWS_EXECUTION_ENV"):  # Simulación para tests locales
        return "fake-id", "fake-secret"

    # En AWS Real o LocalStack Pro
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
            job_id = payload.get("jobId")
            user_id = payload.get("userId")

            # [CAMBIO PK/SK]: Definimos las llaves de acceso según el nuevo esquema
            # Esto nos permite ir directo al registro del usuario sin hacer Scan
            target_key = {"PK": f"USER#{user_id}", "SK": f"JOB#{job_id}"}

            logger.info(f"Procesando Job: {job_id} para Usuario: {user_id}")

            # B. Recuperar Estado y Metadatos
            # [CAMBIO PK/SK]: Usamos la llave compuesta para leer
            job_response = table.get_item(Key=target_key)
            job_item = job_response.get("Item", {})

            if not job_item:
                logger.error(f"No se encontró el Job {job_id} en la base de datos.")
                continue

            job_type = job_item.get("type", "EXPORT")
            encrypted_refresh_token = job_item.get("encryptedRefreshToken")
            current_page_token = job_item.get("nextPageToken")

            # C. Fase de Identidad
            client_id, client_secret = get_google_secrets()

            try:
                refresh_token = decrypt_token(kms_client, encrypted_refresh_token)
            except (binascii.Error, ValueError) as e:
                logger.error(f"Token corrupto para el usuario {user_id}")
                continue

            access_token = refresh_access_token(client_id, client_secret, refresh_token)
            yt = YouTubeClient(access_token)

            # D. Ejecución de Lógica (Bifurcación)
            if job_type == "IMPORT":
                s3_key = f"uploads/{user_id}/{job_id}.json"
                s3_res = s3.get_object(Bucket=bucket_name, Key=s3_key)
                data_to_import = json.loads(s3_res["Body"].read().decode("utf-8"))
                items_processed_count = len(data_to_import)
                next_page_token = None
            else:
                yt_res = yt.get_subscriptions(
                    max_results=50, page_token=current_page_token
                )
                items_processed_count = len(yt_res.get("items", []))
                next_page_token = yt_res.get("nextPageToken")

            # E. Actualización de Progreso (Atómica)
            # [CAMBIO PK/SK]: Usamos la llave compuesta para actualizar
            table.update_item(
                Key=target_key,
                UpdateExpression="SET #s = :run, nextPageToken = :next, updatedAt = :now ADD doneCount :inc",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":run": "RUNNING",
                    ":next": next_page_token,
                    ":inc": items_processed_count,
                    ":now": datetime.datetime.now(datetime.UTC).isoformat(),
                },
            )

            # F. Lógica de Relevo (Relay Pattern)
            if next_page_token:
                sqs.send_message(
                    QueueUrl=queue_url,
                    MessageBody=json.dumps({"jobId": job_id, "userId": user_id}),
                )
            else:
                # [CAMBIO PK/SK]: Marcamos como finalizado
                table.update_item(
                    Key=target_key,
                    UpdateExpression="SET #s = :done, updatedAt = :now",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={
                        ":done": "DONE",
                        ":now": datetime.datetime.now(datetime.UTC).isoformat(),
                    },
                )

        except QuotaExceededError:
            # [CAMBIO PK/SK]: Pausamos el trabajo
            table.update_item(
                Key=target_key,
                UpdateExpression="SET #s = :paused, updatedAt = :now",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":paused": "PAUSED_QUOTA",
                    ":now": datetime.datetime.now(datetime.UTC).isoformat(),
                },
            )
            return {"status": "paused"}

        except Exception as e:
            logger.exception(f"Fallo crítico en el Worker")
            raise e

    return {"status": "processed"}
