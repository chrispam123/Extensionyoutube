# -*- coding: utf-8 -*-
"""
Project: Nocturne Backend
Component: Worker Lambda
Purpose: Process YouTube subscriptions/playlists and accumulate results in S3.
         Supports Single Table Design, Atomic Counters, and Quota Management.
"""

import binascii
import datetime
import json
import os
import time

import boto3
from aws_lambda_powertools import Logger, Tracer
from botocore.exceptions import ClientError

from shared.exceptions import InvalidTokenError, QuotaExceededError
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

# Caché global para evitar llamadas excesivas a SSM
cached_secrets = {"client_id": None, "client_secret": None}


def get_google_secrets():
    """Recupera secretos de SSM con caché en memoria y descifrado KMS."""
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
    table_name = os.getenv("DYNAMODB_TABLE")
    table = dynamo.Table(table_name)
    queue_url = os.getenv("SQS_QUEUE_URL")
    bucket_name = os.getenv("S3_BUCKET")

    for record in event.get("Records", []):
        try:
            # A. PARSEO DEL MENSAJE (Contrato SQS)
            payload = json.loads(record["body"])
            job_id = payload.get("jobId")
            user_id = payload.get("userId")

            if not job_id or not user_id:
                logger.error("❌ Mensaje mal formado en SQS. Saltando...")
                continue

            # Coordenadas de Single Table Design
            job_key = {"PK": f"USER#{user_id}", "SK": f"JOB#{job_id}"}
            profile_key = {"PK": f"USER#{user_id}", "SK": "PROFILE"}

            # B. RECUPERAR ESTADO DESDE EL CEREBRO (DynamoDB)
            profile_item = table.get_item(Key=profile_key).get("Item", {})
            job_item = table.get_item(Key=job_key).get("Item", {})

            if not profile_item or not job_item:
                logger.error(
                    f"❌ No se encontró información para Job {job_id}. Abortando."
                )
                continue

            job_type = job_item.get("type", "EXPORT")
            options = job_item.get("options", {"channels": True, "playlists": False})
            encrypted_token = profile_item.get("encryptedRefreshToken")
            current_page_token = job_item.get("nextPageToken")

            # C. FASE DE IDENTIDAD (KMS + Google OAuth2)
            client_id, client_secret = get_google_secrets()

            try:
                refresh_token = decrypt_token(kms_client, encrypted_token)
                access_token = refresh_access_token(
                    client_id, client_secret, refresh_token
                )
            except Exception as auth_err:
                logger.error(
                    f"❌ Error de autenticación para usuario {user_id}: {str(auth_err)}"
                )
                continue

            yt = YouTubeClient(access_token)

            success_count = 0
            failed_count = 0
            next_token_to_save = None
            has_more = False

            # =================================================================
            # D. EJECUCIÓN DE ESTRATEGIA (Bifurcación de Negocio)
            # =================================================================
            try:
                if job_type == "IMPORT":
                    # --- ESTRATEGIA: SIEMBRA (S3 -> YouTube) ---
                    logger.info(f"📥 Iniciando SIEMBRA (Import) para Job {job_id}")

                    s3_key = f"uploads/{user_id}/{job_id}.json"
                    s3_res = s3.get_object(Bucket=bucket_name, Key=s3_key)
                    raw_data = json.loads(s3_res["Body"].read().decode("utf-8"))

                    # --- VALIDACIÓN DE CONSISTENCIA ---
                    # Verificamos que el archivo tenga un formato procesable
                    if not isinstance(raw_data, list) and "channels" not in raw_data:
                        logger.error(
                            "❌ Formato de archivo S3 inválido para importación."
                        )
                        table.update_item(
                            Key=job_key,
                            UpdateExpression="SET #s = :f",
                            ExpressionAttributeNames={"#s": "status"},
                            ExpressionAttributeValues={":f": "FAILED"},
                        )
                        continue

                    # Filtrado por opciones
                    work_list = (
                        raw_data
                        if isinstance(raw_data, list)
                        else raw_data.get("channels", [])
                    )

                    # Puntero de lectura: doneCount + failedCount
                    start_index = int(job_item.get("doneCount", 0)) + int(
                        job_item.get("failedCount", 0)
                    )
                    batch_size = 10
                    end_index = start_index + batch_size
                    batch = work_list[start_index:end_index]

                    logger.info(
                        f"🚜 Procesando lote {start_index} al {end_index} de {len(work_list)}"
                    )

                    for item in batch:
                        try:
                            # LLAMADA REAL A YOUTUBE
                            yt.subscribe_to_channel(item["channelId"])
                            logger.info(f"✅ Vinculado: {item.get('title')}")
                            success_count += 1

                        # --- RE-LANZAMIENTO INMEDIATO DE CUOTA ---
                        # Evitamos que el 'except Exception' de abajo capture la cuota agotada
                        except QuotaExceededError as qe:
                            logger.warning(
                                "🛑 Cuota agotada en mitad del lote. Elevando excepción..."
                            )
                            raise qe

                        except Exception as e:
                            logger.error(
                                f"❌ Error en item {item.get('title')}: {str(e)}"
                            )
                            failed_count += 1

                    has_more = end_index < len(work_list)

                else:
                    # --- ESTRATEGIA: COSECHA (YouTube -> S3) ---
                    logger.info(f"📤 Iniciando COSECHA (Export) para Job {job_id}")

                    yt_res = yt.get_subscriptions(
                        max_results=50, page_token=current_page_token
                    )
                    items = yt_res.get("items", [])
                    next_token_to_save = yt_res.get("nextPageToken")

                    new_data = []
                    for item in items:
                        snippet = item.get("snippet", {})
                        new_data.append(
                            {
                                "id": item.get("id"),
                                "title": snippet.get("title"),
                                "channelId": snippet.get("resourceId", {}).get(
                                    "channelId"
                                ),
                                "thumbnail": snippet.get("thumbnails", {})
                                .get("default", {})
                                .get("url"),
                            }
                        )

                    s3_key = f"exports/{user_id}/{job_id}.json"
                    accumulated = []
                    try:
                        existing = s3.get_object(Bucket=bucket_name, Key=s3_key)
                        accumulated = json.loads(
                            existing["Body"].read().decode("utf-8")
                        )
                    except ClientError as e:
                        if e.response["Error"]["Code"] != "NoSuchKey":
                            raise

                    accumulated.extend(new_data)
                    s3.put_object(
                        Bucket=bucket_name,
                        Key=s3_key,
                        Body=json.dumps(accumulated),
                        ContentType="application/json",
                    )

                    success_count = len(new_data)
                    has_more = next_token_to_save is not None

                # =================================================================
                # E. ACTUALIZACIÓN ATÓMICA Y RELEVO
                # =================================================================
                now = datetime.datetime.now(datetime.UTC).isoformat()

                table.update_item(
                    Key=job_key,
                    UpdateExpression="SET #s = :run, nextPageToken = :next, updatedAt = :now ADD doneCount :s, failedCount :f",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={
                        ":run": "RUNNING",
                        ":next": next_token_to_save,
                        ":s": success_count,
                        ":f": failed_count,
                        ":now": now,
                    },
                )

                if has_more:
                    logger.info(f"🔄 Re-encolando relevo para Job {job_id}")
                    sqs.send_message(
                        QueueUrl=queue_url, MessageBody=json.dumps(payload)
                    )
                else:
                    logger.info(f"🏁 Misión cumplida para Job {job_id}")
                    table.update_item(
                        Key=job_key,
                        UpdateExpression="SET #s = :done, updatedAt = :now",
                        ExpressionAttributeNames={"#s": "status"},
                        ExpressionAttributeValues={":done": "DONE", ":now": now},
                    )

            except QuotaExceededError:
                # CAPTURA DE CUOTA: Pausamos el Job para el Resumer
                logger.warning(
                    f"⚠️ Límite de Google alcanzado para Job {job_id}. Hibernando."
                )
                table.update_item(
                    Key=job_key,
                    UpdateExpression="SET #s = :paused, updatedAt = :now",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={
                        ":paused": "PAUSED_QUOTA",
                        ":now": datetime.datetime.now(datetime.UTC).isoformat(),
                    },
                )
                return {"status": "paused_by_quota"}

        except Exception as e:
            logger.exception(f"🔥 Fallo crítico en el Worker: {str(e)}")
            raise e

    return {"status": "processed"}
