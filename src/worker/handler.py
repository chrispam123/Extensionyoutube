# -*- coding: utf-8 -*-
"""
Project: Nocturne Backend
Component: Worker Lambda (YouTube Integration + Relay Pattern)
"""

import binascii
import json
import os

import boto3
from aws_lambda_powertools import Logger, Tracer

from shared.exceptions import InvalidTokenError, QuotaExceededError
from shared.google_auth import refresh_access_token

# Importaciones de nuestra capa Shared
from shared.security import decrypt_token
from shared.youtube_client import YouTubeClient

# 1. Configuración de Observabilidad
logger = Logger()
tracer = Tracer()

# 2. Caché Global (Warm Start)
cached_secrets = {"client_id": None, "client_secret": None}

# 3. Inicialización de Clientes AWS
RAW_ENDPOINT = os.getenv("AWS_ENDPOINT_URL")
ENDPOINT_URL = RAW_ENDPOINT if RAW_ENDPOINT and RAW_ENDPOINT.strip() else None

s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL)
dynamo = boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL)
kms_client = boto3.client("kms", endpoint_url=ENDPOINT_URL)
ssm = boto3.client("ssm", endpoint_url=ENDPOINT_URL)
sqs = boto3.client("sqs", endpoint_url=ENDPOINT_URL)


def get_google_secrets():
    """Recupera los secretos de Google desde SSM o del caché global."""
    if not cached_secrets["client_id"] or not cached_secrets["client_secret"]:
        logger.info("Caché de secretos vacío. Consultando SSM...")
        cached_secrets["client_id"] = ssm.get_parameter(
            Name="/extension/google/client_id", WithDecryption=True
        )["Parameter"]["Value"]
        cached_secrets["client_secret"] = ssm.get_parameter(
            Name="/extension/google/client_secret", WithDecryption=True
        )["Parameter"]["Value"]
    return cached_secrets["client_id"], cached_secrets["client_secret"]


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    table_name = os.getenv("DYNAMODB_TABLE")
    table = dynamo.Table(table_name)
    queue_url = os.getenv("SQS_QUEUE_URL")
    bucket_name = os.getenv("S3_BUCKET")

    for record in event.get("Records", []):
        try:
            # A. Identificación del Trabajo
            payload = json.loads(record["body"])
            job_id = payload.get("jobId")
            user_id = payload.get("userId")

            logger.info(f"Procesando Job: {job_id} para Usuario: {user_id}")

            # B. Recuperar Estado y Metadatos de DynamoDB
            job_response = table.get_item(Key={"jobId": job_id})
            job_item = job_response.get("Item", {})

            job_type = job_item.get("type", "EXPORT")  # IMPORT o EXPORT
            encrypted_refresh_token = job_item.get("encryptedRefreshToken")
            current_page_token = job_item.get("nextPageToken")

            # C. Fase de Identidad (KMS + Google OAuth2)
            client_id, client_secret = get_google_secrets()

            if not encrypted_refresh_token:
                logger.error(f"No hay token para el Job {job_id}. Abortando.")
                continue

            try:
                refresh_token = decrypt_token(kms_client, encrypted_refresh_token)
            except (binascii.Error, ValueError) as e:
                logger.error(f"Token inválido en DynamoDB: {str(e)}")
                continue

            access_token = refresh_access_token(client_id, client_secret, refresh_token)
            yt = YouTubeClient(access_token)

            # =================================================================
            # D. BIFURCACIÓN DE LÓGICA DE NEGOCIO
            # =================================================================

            if job_type == "IMPORT":
                # --- CASO IMPORTACIÓN: Leer de S3 y procesar ---
                # En una importación real, aquí leeríamos el JSON de S3 para saber
                # a qué canales suscribir al usuario.
                s3_key = f"uploads/{user_id}/{job_id}.json"
                logger.info(
                    f"Modo IMPORT: Leyendo carga útil desde s3://{bucket_name}/{s3_key}"
                )

                s3_response = s3.get_object(Bucket=bucket_name, Key=s3_key)
                raw_data = s3_response["Body"].read().decode("utf-8")
                data_to_import = json.loads(raw_data)

                # (Aquí iría la lógica de llamar a yt.subscribe_to_channel() en bucle)
                items_processed_count = len(data_to_import)  # Simplificado para el MVP
                next_page_token = None  # Las importaciones de archivo suelen ser de un solo lote o gestionadas por índice

            else:
                # --- CASO EXPORTACIÓN: Leer de YouTube API ---
                logger.info(f"Modo EXPORT: Consultando suscripciones a YouTube API")
                try:
                    yt_response = yt.get_subscriptions(
                        max_results=50, page_token=current_page_token
                    )
                    items = yt_response.get("items", [])
                    next_page_token = yt_response.get("nextPageToken")
                    items_processed_count = len(items)
                except QuotaExceededError:
                    raise  # Se captura en el bloque externo

            # =================================================================
            # E. ACTUALIZACIÓN DE PROGRESO Y RELEVO
            # =================================================================

            table.update_item(
                Key={"jobId": job_id},
                UpdateExpression="SET #s = :run, nextPageToken = :next ADD doneCount :inc",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":run": "RUNNING",
                    ":next": next_page_token,
                    ":inc": items_processed_count,
                },
            )

            if next_page_token:
                logger.info(f"Re-encolando relevo para página: {next_page_token}")
                sqs.send_message(
                    QueueUrl=queue_url,
                    MessageBody=json.dumps({"jobId": job_id, "userId": user_id}),
                )
            else:
                logger.info(f"Job {job_id} finalizado con éxito.")
                table.update_item(
                    Key={"jobId": job_id},
                    UpdateExpression="SET #s = :done",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={":done": "DONE"},
                )

        except QuotaExceededError:
            logger.warning(f"Cuota agotada para el Job {job_id}. Pausando...")
            table.update_item(
                Key={"jobId": job_id},
                UpdateExpression="SET #s = :paused",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":paused": "PAUSED_QUOTA"},
            )
            return {"status": "paused_by_quota"}

        except Exception as e:
            logger.exception(f"Error crítico en el Worker: {str(e)}")
            raise e

    return {"status": "processed"}
