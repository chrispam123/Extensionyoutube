# -*- coding: utf-8 -*-
"""
Project: Nocturne Backend
Component: Worker Lambda
Purpose: Full Import/Export engine with Playlist support and Single Table Design.
"""

import datetime
import json
import os

import boto3
from aws_lambda_powertools import Logger, Tracer
from botocore.exceptions import ClientError

from shared.exceptions import InvalidTokenError, QuotaExceededError
from shared.google_auth import refresh_access_token
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

cached_secrets = {"client_id": None, "client_secret": None}


def get_google_secrets():
    if not cached_secrets["client_id"] or not cached_secrets["client_secret"]:
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
        # ---------------------------------------------------------------
        # Estas variables deben ser accesibles desde los bloques except
        # exteriores (QuotaExceededError usa job_key)
        # ---------------------------------------------------------------
        job_key = None

        try:
            payload = json.loads(record["body"])
            job_id, user_id = payload.get("jobId"), payload.get("userId")
            job_key = {"PK": f"USER#{user_id}", "SK": f"JOB#{job_id}"}
            profile_key = {"PK": f"USER#{user_id}", "SK": "PROFILE"}

            # A. RECUPERAR ESTADO COMPLETO
            profile_item = table.get_item(Key=profile_key).get("Item", {})
            job_item = table.get_item(Key=job_key).get("Item", {})

            if not profile_item or not job_item:
                logger.error(f"❌ Datos faltantes para Job {job_id}")
                continue

            job_type = job_item.get("type", "EXPORT")
            options = job_item.get("options", {"channels": True, "playlists": False})

            # Punteros de Playlist
            curr_pl_idx = int(job_item.get("currentPlaylistIndex", 0))
            curr_vid_idx = int(job_item.get("currentVideoIndex", 0))
            active_pl_id = job_item.get("activePlaylistId")

            # B. AUTENTICACIÓN
            cid, csec = get_google_secrets()
            refresh_token = decrypt_token(
                kms_client, profile_item.get("encryptedRefreshToken")
            )
            access_token = refresh_access_token(cid, csec, refresh_token)
            yt = YouTubeClient(access_token)

            success_count = 0
            failed_count = 0
            has_more = False
            next_page_token = job_item.get("nextPageToken")

            # =================================================================
            # C. LÓGICA DE IMPORTACIÓN (SIEMBRA)
            # =================================================================
            if job_type == "IMPORT":
                s3_res = s3.get_object(
                    Bucket=bucket_name, Key=f"uploads/{user_id}/{job_id}.json"
                )
                raw_data = json.loads(s3_res["Body"].read().decode("utf-8"))

                # --- VALIDACIÓN DE FORMATO ---
                if not isinstance(raw_data, (list, dict)):
                    logger.error("❌ Formato de archivo S3 inválido para importación.")
                    table.update_item(
                        Key=job_key,
                        UpdateExpression="SET #s = :f, updatedAt = :now",
                        ExpressionAttributeNames={"#s": "status"},
                        ExpressionAttributeValues={
                            ":f": "FAILED",
                            ":now": datetime.datetime.now(datetime.UTC).isoformat(),
                        },
                    )
                    continue

                channels = (
                    raw_data.get("channels", [])
                    if isinstance(raw_data, dict)
                    else raw_data
                )
                playlists = (
                    raw_data.get("playlists", []) if isinstance(raw_data, dict) else []
                )

                # FASE 1: CANALES
                total_processed_channels = int(job_item.get("doneCount", 0)) + int(
                    job_item.get("failedCount", 0)
                )

                if options.get("channels") and total_processed_channels < len(channels):
                    logger.info(
                        f"🚜 Procesando Canales (Lote desde {total_processed_channels})"
                    )
                    batch = channels[
                        total_processed_channels : total_processed_channels + 10
                    ]
                    for chan in batch:
                        try:
                            yt.subscribe_to_channel(
                                chan["channelId"]
                            )  # aqui suscribimos a youtubereal
                            success_count += 1
                        except QuotaExceededError:
                            raise
                        except Exception:
                            failed_count += 1

                    # Solo hay más trabajo si quedan canales por procesar O si
                    # las playlists están activadas Y realmente existen
                    more_channels = (total_processed_channels + len(batch)) < len(
                        channels
                    )
                    more_playlists = options.get("playlists") and len(playlists) > 0
                    has_more = more_channels or more_playlists

                # FASE 2: PLAYLISTS (Solo si terminamos canales o no había)
                elif options.get("playlists") and curr_pl_idx < len(playlists):
                    logger.info(f"📜 Procesando Playlists (Índice {curr_pl_idx})")
                    current_pl = playlists[curr_pl_idx]

                    # 1. Crear la playlist si no existe en este relevo
                    if not active_pl_id:
                        logger.info(f"✨ Creando nueva playlist: {current_pl['title']}")
                        pl_resp = yt.create_playlist(current_pl["title"])
                        active_pl_id = pl_resp["id"]
                        # Guardamos el ID inmediatamente para no duplicar
                        table.update_item(
                            Key=job_key,
                            UpdateExpression="SET activePlaylistId = :id",
                            ExpressionAttributeValues={":id": active_pl_id},
                        )

                    # 2. Añadir videos en lotes de 10
                    videos = current_pl.get("videos", [])
                    batch_vids = videos[curr_vid_idx : curr_vid_idx + 10]
                    logger.info(
                        f"🎬 Añadiendo videos {curr_vid_idx} al "
                        f"{curr_vid_idx + len(batch_vids)}"
                    )

                    for vid_id in batch_vids:
                        try:
                            yt.add_video_to_playlist(active_pl_id, vid_id)
                            success_count += 1
                        except QuotaExceededError:
                            raise
                        except Exception:
                            failed_count += 1

                    curr_vid_idx += len(batch_vids)

                    # 3. ¿Terminamos esta playlist?
                    if curr_vid_idx >= len(videos):
                        curr_pl_idx += 1
                        curr_vid_idx = 0
                        active_pl_id = None  # Reset para la siguiente

                    has_more = curr_pl_idx < len(playlists)

            # =================================================================
            # D. LÓGICA DE EXPORTACIÓN (COSECHA)
            # =================================================================
            else:
                logger.info("📤 Iniciando COSECHA (Export)")
                yt_res = yt.get_subscriptions(
                    max_results=50, page_token=next_page_token
                )
                items = yt_res.get("items", [])
                next_page_token = yt_res.get("nextPageToken")

                new_data = []
                for item in items:
                    snippet = item.get("snippet", {})
                    new_data.append(
                        {
                            "id": item.get("id"),
                            "title": snippet.get("title"),
                            "channelId": snippet.get("resourceId", {}).get("channelId"),
                            "thumbnail": snippet.get("thumbnails", {})
                            .get("default", {})
                            .get("url"),
                        }
                    )

                # Acumulación persistente en S3
                s3_key = f"exports/{user_id}/{job_id}.json"
                accumulated = []
                try:
                    existing = s3.get_object(Bucket=bucket_name, Key=s3_key)
                    accumulated = json.loads(existing["Body"].read().decode("utf-8"))
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
                has_more = next_page_token is not None

            # =================================================================
            # E. ACTUALIZACIÓN DE ESTADO FINAL
            # =================================================================
            now = datetime.datetime.now(datetime.UTC).isoformat()

            # Construimos la expresión dinámicamente: si active_pl_id es None
            # usamos REMOVE, si tiene valor usamos SET.
            # DynamoDB no acepta None en ExpressionAttributeValues.
            if active_pl_id is not None:
                update_expr = (
                    "SET #s = :run, nextPageToken = :next, updatedAt = :now, "
                    "currentPlaylistIndex = :cpi, currentVideoIndex = :cvi, "
                    "activePlaylistId = :api "
                    "ADD doneCount :s, failedCount :f"
                )
                expr_values = {
                    ":run": "RUNNING",
                    ":next": next_page_token,
                    ":s": success_count,
                    ":f": failed_count,
                    ":now": now,
                    ":cpi": curr_pl_idx,
                    ":cvi": curr_vid_idx,
                    ":api": active_pl_id,
                }
            else:
                update_expr = (
                    "SET #s = :run, nextPageToken = :next, updatedAt = :now, "
                    "currentPlaylistIndex = :cpi, currentVideoIndex = :cvi "
                    "REMOVE activePlaylistId "
                    "ADD doneCount :s, failedCount :f"
                )
                expr_values = {
                    ":run": "RUNNING",
                    ":next": next_page_token,
                    ":s": success_count,
                    ":f": failed_count,
                    ":now": now,
                    ":cpi": curr_pl_idx,
                    ":cvi": curr_vid_idx,
                }

            table.update_item(
                Key=job_key,
                UpdateExpression=update_expr,
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues=expr_values,
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

        except QuotaExceededError:
            # job_key puede ser None si el mensaje SQS estaba mal formado
            if job_key is not None:
                table.update_item(
                    Key=job_key,
                    UpdateExpression="SET #s = :p, updatedAt = :now",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={
                        ":p": "PAUSED_QUOTA",
                        ":now": datetime.datetime.now(datetime.UTC).isoformat(),
                    },
                )
            return {"status": "paused"}
        except Exception as e:
            logger.exception("🔥 Fallo crítico")
            raise e

    return {"status": "processed"}
