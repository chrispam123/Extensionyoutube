# -*- coding: utf-8 -*-
import datetime
import json
import os
import time

import boto3
from aws_lambda_powertools import Logger, Tracer
from botocore.exceptions import ClientError

from shared.exceptions import InvalidTokenError, QuotaExceededError
from shared.google_auth import refresh_access_token
from shared.security import decrypt_token
from shared.youtube_client import YouTubeClient

logger = Logger()
tracer = Tracer()

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
        job_key = None
        try:
            payload = json.loads(record["body"])
            job_id, user_id = payload.get("jobId"), payload.get("userId")
            job_key = {"PK": f"USER#{user_id}", "SK": f"JOB#{job_id}"}
            profile_key = {"PK": f"USER#{user_id}", "SK": "PROFILE"}

            profile_item = table.get_item(Key=profile_key).get("Item", {})
            job_item = table.get_item(Key=job_key).get("Item", {})

            if not profile_item or not job_item:
                logger.error(f"❌ Datos faltantes para Job {job_id}")
                continue

            job_type = job_item.get("type", "EXPORT")
            options = job_item.get("options", {"channels": True, "playlists": False})
            curr_pl_idx = int(job_item.get("currentPlaylistIndex", 0))
            curr_vid_idx = int(job_item.get("currentVideoIndex", 0))
            active_pl_id = job_item.get("activePlaylistId")
            next_page_token = job_item.get("nextPageToken")
            # Export de playlists: cola de trabajo y cursor actual
            pending_playlists = job_item.get("pendingPlaylists")
            exp_playlist_id = job_item.get("currentPlaylistId")
            exp_playlist_title = job_item.get("currentPlaylistTitle")
            # Token separado para playlistItems — evita que contamine el de canales
            playlist_page_token = job_item.get("playlistPageToken")

            logger.info(
                "🚀 Worker iniciando relevo",
                extra={
                    "job_id": job_id,
                    "user_id": user_id,
                    "type": job_type,
                    "done_count": int(job_item.get("doneCount", 0)),
                    "failed_count": int(job_item.get("failedCount", 0)),
                },
            )

            cid, csec = get_google_secrets()
            refresh_token = decrypt_token(
                kms_client, profile_item.get("encryptedRefreshToken")
            )
            access_token = refresh_access_token(cid, csec, refresh_token)
            yt = YouTubeClient(access_token)

            success_count = 0
            failed_count = 0
            has_more = False

            # =================================================================
            # C. LÓGICA DE IMPORTACIÓN (SIEMBRA)
            # =================================================================
            if job_type == "IMPORT":
                s3_res = s3.get_object(
                    Bucket=bucket_name, Key=f"uploads/{user_id}/{job_id}.json"
                )
                raw_data = json.loads(s3_res["Body"].read().decode("utf-8"))

                if not isinstance(raw_data, (list, dict)):
                    logger.error("❌ Formato S3 inválido")
                    table.update_item(
                        Key=job_key,
                        UpdateExpression="SET #s = :f, expiresAt = :ttl, updatedAt = :now",
                        ExpressionAttributeNames={"#s": "status"},
                        ExpressionAttributeValues={
                            ":f": "FAILED",
                            ":ttl": int(time.time()) + (6 * 86400),
                            ":now": datetime.datetime.now(datetime.UTC).isoformat(),
                        },
                    )
                    continue

                channels = (
                    raw_data
                    if isinstance(raw_data, list)
                    else raw_data.get("channels", [])
                )
                playlists = (
                    raw_data.get("playlists", []) if isinstance(raw_data, dict) else []
                )

                total_processed = int(job_item.get("doneCount", 0)) + int(
                    job_item.get("failedCount", 0)
                )

                if options.get("channels") and total_processed < len(channels):
                    batch = channels[total_processed : total_processed + 10]
                    logger.info(
                        f"🚜 Procesando lote de canales",
                        extra={
                            "job_id": job_id,
                            "batch_start": total_processed,
                            "batch_end": total_processed + len(batch),
                            "total_channels": len(channels),
                        },
                    )
                    for chan in batch:
                        try:
                            result = yt.subscribe_to_channel(chan["channelId"])
                            success_count += 1
                            if result.get("status") == "already_exists":
                                logger.info(f"♻️ Ya vinculado: {chan.get('title')}")
                            else:
                                logger.info(f"✅ Nuevo vínculo: {chan.get('title')}")
                        except QuotaExceededError:
                            raise
                        except Exception as exc:
                            logger.warning(
                                f"⚠️ Fallo real en canal",
                                extra={
                                    "job_id": job_id,
                                    "channel_title": chan.get("title"),
                                    "error": str(exc),
                                },
                            )
                            failed_count += 1
                    has_more = (total_processed + len(batch)) < len(channels) or (
                        options.get("playlists") and len(playlists) > 0
                    )

                elif options.get("playlists") and curr_pl_idx < len(playlists):
                    current_pl = playlists[curr_pl_idx]
                    logger.info(
                        f"📜 Procesando playlist",
                        extra={
                            "job_id": job_id,
                            "playlist_index": curr_pl_idx,
                            "playlist_title": current_pl.get("title"),
                            "total_playlists": len(playlists),
                        },
                    )
                    if not active_pl_id:
                        pl_resp = yt.create_playlist(current_pl["title"])
                        active_pl_id = pl_resp["id"]
                        table.update_item(
                            Key=job_key,
                            UpdateExpression="SET activePlaylistId = :id",
                            ExpressionAttributeValues={":id": active_pl_id},
                        )

                    videos = current_pl.get("videos", [])
                    batch_vids = videos[curr_vid_idx : curr_vid_idx + 10]
                    for vid_item in batch_vids:
                        # Extraer el ID: puede ser string directo o dict {videoId, title}
                        vid_id = (
                            vid_item
                            if isinstance(vid_item, str)
                            else vid_item.get("videoId")
                        )
                        try:
                            yt.add_video_to_playlist(active_pl_id, vid_id)
                            success_count += 1
                        except QuotaExceededError:
                            raise
                        except Exception as exc:
                            logger.warning(
                                f"⚠️ Fallo al añadir video",
                                extra={
                                    "job_id": job_id,
                                    "playlist_id": active_pl_id,
                                    "video_id": vid_id,
                                    "error": str(exc),
                                },
                            )
                            failed_count += 1

                    curr_vid_idx += len(batch_vids)
                    if curr_vid_idx >= len(videos):
                        curr_pl_idx += 1
                        curr_vid_idx = 0
                        active_pl_id = None
                    has_more = curr_pl_idx < len(playlists)

            # =================================================================
            # D. LÓGICA DE EXPORTACIÓN (COSECHA EN DOS FASES)
            # =================================================================
            else:
                s3_key = f"exports/{user_id}/{job_id}.json"
                accumulated = {"channels": [], "playlists": []}
                try:
                    existing = s3.get_object(Bucket=bucket_name, Key=s3_key)
                    accumulated = json.loads(existing["Body"].read().decode("utf-8"))
                except ClientError as e:
                    if e.response["Error"]["Code"] != "NoSuchKey":
                        raise

                # FASE 1: CANALES
                if options.get("channels") and next_page_token != "CHANNELS_DONE":
                    logger.info(
                        "📤 Cosechando Canales...",
                        extra={
                            "job_id": job_id,
                            "page_token": next_page_token or "(initial)",
                        },
                    )
                    yt_res = yt.get_subscriptions(
                        max_results=50, page_token=next_page_token
                    )
                    for item in yt_res.get("items", []):
                        snippet = item.get("snippet", {})
                        accumulated["channels"].append(
                            {
                                "id": item.get("id"),
                                "title": snippet.get("title"),
                                "channelId": snippet.get("resourceId", {}).get(
                                    "channelId"
                                ),
                            }
                        )
                    success_count = len(yt_res.get("items", []))
                    next_page_token = yt_res.get("nextPageToken") or "CHANNELS_DONE"
                    has_more = (next_page_token != "CHANNELS_DONE") or options.get(
                        "playlists"
                    )

                # FASE 2: EXPORTACIÓN DE PLAYLISTS
                elif options.get("playlists"):
                    # === SUB-FASE A: DISCOVERY (Inventario de playlists) ===
                    if pending_playlists is None:
                        logger.info("🔍 Descubriendo playlists del usuario...")
                        all_pl = []
                        pl_page_token = None
                        while True:
                            pl_res = yt.get_playlists(page_token=pl_page_token)
                            for pl in pl_res.get("items", []):
                                all_pl.append(
                                    {
                                        "id": pl["id"],
                                        "title": pl["snippet"]["title"],
                                    }
                                )
                            pl_page_token = pl_res.get("nextPageToken")
                            if not pl_page_token:
                                break

                        pending_playlists = all_pl
                        logger.info(
                            f"📋 {len(all_pl)} playlists descubiertas",
                            extra={"job_id": job_id},
                        )
                        has_more = len(pending_playlists) > 0

                    # === SUB-FASE B: DRAIN (Vaciado de videos por playlist) ===
                    elif len(pending_playlists) > 0:
                        # Si no hay playlist activa, tomamos la primera de la cola
                        if exp_playlist_id is None:
                            first = pending_playlists[0]
                            exp_playlist_id = first["id"]
                            exp_playlist_title = first["title"]
                            playlist_page_token = None
                            logger.info(
                                f"📜 Drenando playlist: {exp_playlist_title}",
                                extra={"job_id": job_id},
                            )

                        # Extraer videos
                        pl_items = yt.get_playlist_items(
                            exp_playlist_id,
                            page_token=playlist_page_token,
                        )

                        # Encontrar o crear entrada en accumulated
                        pl_entry = None
                        for p in accumulated["playlists"]:
                            if p["playlistId"] == exp_playlist_id:
                                pl_entry = p
                                break
                        if pl_entry is None:
                            pl_entry = {
                                "playlistId": exp_playlist_id,
                                "title": exp_playlist_title or "",
                                "videos": [],
                            }
                            accumulated["playlists"].append(pl_entry)

                        for item in pl_items.get("items", []):
                            snippet = item.get("snippet", {})
                            pl_entry["videos"].append(
                                {
                                    "videoId": snippet.get("resourceId", {}).get(
                                        "videoId"
                                    ),
                                    "title": snippet.get("title"),
                                }
                            )
                            success_count += 1

                        # Línea 329-331: playlist_page_token en vez de next_page_token
                        playlist_page_token = pl_items.get("nextPageToken")
                        batch_size = len(pl_items.get("items", []))
                        logger.info(
                            f"🎬 {batch_size} videos añadidos a {exp_playlist_title}",
                            extra={"job_id": job_id},
                        )

                        # ¿Terminamos esta playlist?
                        if playlist_page_token is None:
                            pending_playlists = pending_playlists[1:]
                            exp_playlist_id = None
                            exp_playlist_title = None

                        has_more = len(pending_playlists) > 0

                    else:
                        has_more = False

                s3.put_object(
                    Bucket=bucket_name,
                    Key=s3_key,
                    Body=json.dumps(accumulated),
                    ContentType="application/json",
                )

            # =================================================================
            # E. ACTUALIZACIÓN DE ESTADO FINAL
            # =================================================================
            now = datetime.datetime.now(datetime.UTC).isoformat()

            # Construcción dinámica de la expresión para evitar errores con None
            # Orden correcto DynamoDB: SET (comas) → REMOVE (espacios) → ADD (espacios)
            set_parts = [
                "#s = :run",
                "nextPageToken = :next",
                "updatedAt = :now",
                "currentPlaylistIndex = :cpi",
                "currentVideoIndex = :cvi",
            ]
            remove_parts = []
            expr_attr_names = {"#s": "status"}
            expr_values = {
                ":run": "RUNNING",
                ":next": next_page_token,
                ":now": now,
                ":cpi": curr_pl_idx,
                ":cvi": curr_vid_idx,
            }

            if active_pl_id:
                set_parts.append("activePlaylistId = :api")
                expr_values[":api"] = active_pl_id
            elif job_item.get("activePlaylistId") is not None:
                remove_parts.append("activePlaylistId")

            # Export de playlists: campos de estado
            if pending_playlists is not None:
                set_parts.append("pendingPlaylists = :ppl")
                expr_values[":ppl"] = pending_playlists
            if playlist_page_token is not None:
                set_parts.append("playlistPageToken = :ppt")
                expr_values[":ppt"] = playlist_page_token
            elif job_item.get("playlistPageToken") is not None:
                remove_parts.append("playlistPageToken")
            if exp_playlist_id:
                set_parts.append("currentPlaylistId = :cpid")
                set_parts.append("currentPlaylistTitle = :cpt")
                expr_values[":cpid"] = exp_playlist_id
                expr_values[":cpt"] = exp_playlist_title
            else:
                if job_item.get("currentPlaylistId") is not None:
                    remove_parts.append("currentPlaylistId")
                    remove_parts.append("currentPlaylistTitle")

            # TTL para RUNNING: 6 días de vida mientras esté activo
            set_parts.append("expiresAt = :ttl")
            expr_values[":ttl"] = int(time.time()) + (6 * 86400)

            # Construir la expresión completa
            update_expr = "SET " + ", ".join(set_parts)
            if remove_parts:
                update_expr += " REMOVE " + ", ".join(remove_parts)
            update_expr += " ADD doneCount :s, failedCount :f"
            expr_values[":s"] = success_count
            expr_values[":f"] = failed_count

            table.update_item(
                Key=job_key,
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_attr_names,
                ExpressionAttributeValues=expr_values,
            )

            if has_more:
                logger.info(
                    "🔄 Re-encolando siguiente relevo",
                    extra={"job_id": job_id, "user_id": user_id},
                )
                sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(payload))
            else:
                logger.info(
                    "🏁 Trabajo completado",
                    extra={
                        "job_id": job_id,
                        "total_done": int(job_item.get("doneCount", 0)) + success_count,
                        "total_failed": int(job_item.get("failedCount", 0))
                        + failed_count,
                    },
                )
                table.update_item(
                    Key=job_key,
                    UpdateExpression="SET #s = :done, expiresAt = :ttl, updatedAt = :now",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={
                        ":done": "DONE",
                        ":ttl": int(time.time()) + (6 * 86400),
                        ":now": now,
                    },
                )

        except QuotaExceededError:
            if job_key:
                table.update_item(
                    Key=job_key,
                    UpdateExpression="SET #s = :p, expiresAt = :ttl, updatedAt = :now",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={
                        ":p": "PAUSED_QUOTA",
                        ":ttl": int(time.time()) + (10 * 86400),
                        ":now": datetime.datetime.now(datetime.UTC).isoformat(),
                    },
                )
            return {"status": "paused"}
        except Exception as e:
            logger.exception("🔥 Fallo crítico")
            raise e

    return {"status": "processed"}
