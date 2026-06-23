# -*- coding: utf-8 -*-
"""
Project: Nocturne Backend
Component: Worker Lambda
Purpose: Process YouTube jobs using Single Table Design (PK/SK).
"""

import binascii
import datetime
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

# 2. Caché Global para Secretos (Warm Start)
cached_secrets = {"client_id": None, "client_secret": None}

# 3. Inicialización de Clientes AWS (Fuera del handler)
RAW_ENDPOINT = os.getenv("AWS_ENDPOINT_URL")
ENDPOINT_URL = RAW_ENDPOINT if RAW_ENDPOINT and RAW_ENDPOINT.strip() else None

s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL)
dynamo = boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL)
kms_client = boto3.client("kms", endpoint_url=ENDPOINT_URL)
ssm = boto3.client("ssm", endpoint_url=ENDPOINT_URL)
sqs = boto3.client("sqs", endpoint_url=ENDPOINT_URL)


def get_google_secrets():
    """Recupera secretos de SSM con caché en memoria."""
    if not cached_secrets["client_id"] or not cached_secrets["client_secret"]:
        logger.info("🔍 Consultando secretos de Google en SSM...")
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
    table = dynamo.Table(os.getenv("DYNAMODB_TABLE"))
    queue_url = os.getenv("SQS_QUEUE_URL")
    bucket_name = os.getenv("S3_BUCKET")

    for record in event.get("Records", []):
        try:
            # A. PARSEO DEL MENSAJE
            payload = json.loads(record["body"])
            job_id = payload.get("jobId")
            user_id = payload.get("userId")

            if not job_id or not user_id:
                logger.error("❌ Mensaje mal formado en SQS")
                continue

            # [CAMBIO PK/SK]: Definimos las coordenadas exactas en la Single Table
            job_key = {"PK": f"USER#{user_id}", "SK": f"JOB#{job_id}"}
            profile_key = {"PK": f"USER#{user_id}", "SK": "PROFILE"}

            logger.info(f"🚀 Iniciando Worker para Job: {job_id}")

            # B. RECUPERAR IDENTIDAD (PROFILE)
            # Buscamos el token cifrado en el registro del perfil
            profile_res = table.get_item(Key=profile_key)
            profile_item = profile_res.get("Item", {})
            encrypted_token = profile_item.get("encryptedRefreshToken")

            if not encrypted_token:
                logger.error(
                    f"❌ No se encontró Refresh Token para el usuario {user_id}"
                )
                continue

            # C. RECUPERAR METADATOS DEL TRABAJO (JOB)
            job_res = table.get_item(Key=job_key)
            job_item = job_res.get("Item", {})

            if not job_item:
                logger.error(f"❌ El Job {job_id} no existe en DynamoDB")
                continue

            job_type = job_item.get("type", "EXPORT")
            current_page_token = job_item.get("nextPageToken")

            # D. FASE DE AUTENTICACIÓN
            client_id, client_secret = get_google_secrets()

            try:
                # Desciframos la llave maestra del usuario
                refresh_token = decrypt_token(kms_client, encrypted_token)
                # Obtenemos llave temporal de Google
                access_token = refresh_access_token(
                    client_id, client_secret, refresh_token
                )
            except Exception as auth_err:
                logger.error(f"❌ Fallo de autenticación: {str(auth_err)}")
                continue

            # E. EJECUCIÓN DE LÓGICA (YouTube API)
            yt = YouTubeClient(access_token)

            if job_type == "IMPORT":
                # Lógica de Importación (Leer de S3)
                s3_key = f"uploads/{user_id}/{job_id}.json"
                logger.info(f"📥 Modo IMPORT: Leyendo s3://{bucket_name}/{s3_key}")
                s3_res = s3.get_object(Bucket=bucket_name, Key=s3_key)
                data = json.loads(s3_res["Body"].read().decode("utf-8"))
                items_count = len(data)
                next_page_token = None
            else:
                # Lógica de Exportación (Llamar a YouTube)
                logger.info(f"📤 Modo EXPORT: Consultando YouTube API...")
                yt_res = yt.get_subscriptions(
                    max_results=50, page_token=current_page_token
                )
                items_count = len(yt_res.get("items", []))
                next_page_token = yt_res.get("nextPageToken")

            # F. ACTUALIZACIÓN ATÓMICA DE PROGRESO
            # Usamos la 'job_key' (PK/SK) para actualizar el registro correcto
            table.update_item(
                Key=job_key,
                UpdateExpression="SET #s = :run, nextPageToken = :next, updatedAt = :now ADD doneCount :inc",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":run": "RUNNING",
                    ":next": next_page_token,
                    ":inc": items_count,
                    ":now": datetime.datetime.now(datetime.UTC).isoformat(),
                },
            )

            # G. LÓGICA DE RELEVO (Relay Pattern)
            if next_page_token:
                logger.info(
                    f"🔄 Re-encolando para la siguiente página: {next_page_token}"
                )
                sqs.send_message(
                    QueueUrl=queue_url,
                    MessageBody=json.dumps({"jobId": job_id, "userId": user_id}),
                )
            else:
                logger.info(f"✅ Job {job_id} finalizado.")
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
            logger.warning(f"⚠️ Cuota agotada para Job {job_id}. Pausando...")
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
            logger.exception(f"🔥 Error crítico en el Worker: {str(e)}")
            raise e

    return {"status": "processed"}
