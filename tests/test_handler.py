# -*- coding: utf-8 -*-
"""
Project: Nocturne Backend
Component: Worker Lambda (YouTube Integration + Relay Pattern)
"""

import json
import os
import boto3
import binascii  # NUEVO: Para capturar errores de formato Base64
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger, Tracer

# Importaciones de nuestra capa Shared
from shared.security import decrypt_token
from shared.google_auth import refresh_access_token
from shared.youtube_client import YouTubeClient
from shared.exceptions import QuotaExceededError, InvalidTokenError

# 1. Configuración de Observabilidad
logger = Logger()
tracer = Tracer()

# 2. Caché Global (Fuera del handler para Warm Starts)
cached_secrets = {"client_id": None, "client_secret": None}

# 3. Inicialización de Clientes AWS
ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")
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
            Name="/extension/google/client_id"
        )["Parameter"]["Value"]
        cached_secrets["client_secret"] = ssm.get_parameter(
            Name="/extension/google/client_secret"
        )["Parameter"]["Value"]
    return cached_secrets["client_id"], cached_secrets["client_secret"]


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    table_name = os.getenv("DYNAMODB_TABLE")
    table = dynamo.Table(table_name)
    queue_url = os.getenv("SQS_QUEUE_URL")

    for record in event.get("Records", []):
        try:
            # A. Identificación del Trabajo
            payload = json.loads(record["body"])
            job_id = payload.get("jobId")
            user_id = payload.get("userId")

            logger.info(f"Procesando Job: {job_id} para Usuario: {user_id}")

            # B. Recuperar Estado y Tokens de DynamoDB
            job_response = table.get_item(Key={"jobId": job_id})
            job_item = job_response.get("Item", {})

            encrypted_refresh_token = job_item.get("encryptedRefreshToken")
            current_page_token = job_item.get("nextPageToken")

            # C. Fase de Identidad (KMS + Google OAuth2)
            client_id, client_secret = get_google_secrets()

            if not encrypted_refresh_token:
                logger.error(f"No hay token cifrado para el Job {job_id}. Abortando.")
                continue

            try:
                # Intentamos descifrar
                refresh_token = decrypt_token(kms_client, encrypted_refresh_token)
            except (binascii.Error, ValueError) as e:
                # NUEVO: Captura específica de error de formato Base64
                logger.error(f"El token en DynamoDB no es un Base64 válido: {str(e)}")
                continue

            # Obtenemos un Access Token fresco
            access_token = refresh_access_token(client_id, client_secret, refresh_token)

            # D. Fase de Ejecución (YouTube API)
            yt = YouTubeClient(access_token)

            try:
                yt_response = yt.get_subscriptions(
                    max_results=50, page_token=current_page_token
                )
                items = yt_response.get("items", [])
                next_page_token = yt_response.get("nextPageToken")

                # E. Actualización de Progreso (Atómica)
                table.update_item(
                    Key={"jobId": job_id},
                    UpdateExpression="SET #s = :run, nextPageToken = :next ADD doneCount :inc",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={
                        ":run": "RUNNING",
                        ":next": next_page_token,
                        ":inc": len(items),
                    },
                )

                # F. Lógica de Relevo (Relay Pattern)
                if next_page_token:
                    sqs.send_message(
                        QueueUrl=queue_url,
                        MessageBody=json.dumps({"jobId": job_id, "userId": user_id}),
                    )
                else:
                    table.update_item(
                        Key={"jobId": job_id},
                        UpdateExpression="SET #s = :done",
                        ExpressionAttributeNames={"#s": "status"},
                        ExpressionAttributeValues={":done": "DONE"},
                    )

            except QuotaExceededError:
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
