# -*- coding: utf-8 -*-
import datetime
import json
import os
import time  # NUEVO: Para el cálculo del TTL
import uuid

import boto3
from aws_lambda_powertools import Logger, Tracer

from shared.auth import decode_nocturne_jwt
from shared.responses import cors_response, get_cors_headers

logger = Logger()
tracer = Tracer()

# Clientes AWS (Warm Start)
ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")
if not ENDPOINT_URL or not ENDPOINT_URL.strip():
    ENDPOINT_URL = None

ssm = boto3.client("ssm", endpoint_url=ENDPOINT_URL)
dynamo = boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL)
sqs = boto3.client("sqs", endpoint_url=ENDPOINT_URL)
s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL)


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return {"statusCode": 200, "headers": get_cors_headers()}

    table = dynamo.Table(os.getenv("DYNAMODB_TABLE"))

    try:
        # 1. VALIDACIÓN DE IDENTIDAD
        auth_header = event.get("headers", {}).get("authorization", "")
        token = auth_header.split(" ")[1] if " " in auth_header else ""
        env = os.getenv("ENVIRONMENT", "")
        prefix = f"/extension/{env}" if env else "/extension"
        jwt_secret = ssm.get_parameter(
            Name=f"{prefix}/auth/jwt_secret", WithDecryption=True
        )["Parameter"]["Value"]
        decoded = decode_nocturne_jwt(token, jwt_secret)
        user_id = decoded["sub"]

        # 2. PARSEO DE OPCIONES
        body = json.loads(event.get("body", "{}"))
        job_type = body.get("type", "EXPORT").upper()
        options = body.get("options", {"channels": True, "playlists": False})

        # 3. CHECK DE TRABAJOS ACTIVOS (Evitar duplicados)
        active_jobs = table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
            ExpressionAttributeValues={":pk": f"USER#{user_id}", ":sk": "JOB#"},
        )
        for job in active_jobs.get("Items", []):
            if job.get("status") in [
                "INITIALIZING",
                "PENDING",
                "RUNNING",
                "PAUSED_QUOTA",
            ]:
                return cors_response(
                    409,
                    {
                        "error": "Ya tienes un proceso activo",
                        "jobId": job["jobId"],
                        "status": job["status"],
                    },
                )

        # [NUEVO]: SYNC_CHECK es solo un escaneo, nunca crea trabajo
        if job_type == "SYNC_CHECK":
            return cors_response(200, {"active": False})

        # 4. GENERACIÓN DE IDENTIDAD Y TTL
        job_id = str(uuid.uuid4())
        initial_status = "INITIALIZING" if job_type == "IMPORT" else "PENDING"
        # TTL por estado inicial: IMPORT espera archivo (4h), EXPORT ya está listo (10d)
        TTL_4H = 4 * 3600
        TTL_10D = 10 * 86400
        now_unix = int(time.time())
        expires_at = now_unix + (TTL_4H if job_type == "IMPORT" else TTL_10D)

        # 5. REGISTRO EN DYNAMODB
        table.put_item(
            Item={
                "PK": f"USER#{user_id}",
                "SK": f"JOB#{job_id}",
                "jobId": job_id,
                "userId": user_id,
                "type": job_type,
                "options": options,  # NUEVO: Persistimos la intención
                "status": initial_status,
                "expiresAt": expires_at,  # NUEVO: Fusible de autolimpieza
                "doneCount": 0,
                "failedCount": 0,  # NUEVO: Contador de errores reales
                "createdAt": datetime.datetime.now(datetime.UTC).isoformat(),
            }
        )

        # 6. BIFURCACIÓN
        response_data = {"jobId": job_id, "type": job_type}
        if job_type == "IMPORT":
            s3_key = f"uploads/{user_id}/{job_id}.json"
            upload_url = s3.generate_presigned_url(
                ClientMethod="put_object",
                Params={
                    "Bucket": os.getenv("S3_BUCKET"),
                    "Key": s3_key,
                    "ContentType": "application/json",
                },
                ExpiresIn=300,
            )
            response_data["uploadUrl"] = upload_url
        else:
            sqs.send_message(
                QueueUrl=os.getenv("SQS_QUEUE_URL"),
                MessageBody=json.dumps(
                    {"jobId": job_id, "userId": user_id, "type": job_type}
                ),
            )

        return cors_response(201, response_data)

    except Exception as e:
        logger.exception("Error en Iniciador")
        return cors_response(500, {"error": "Internal Server Error"})
