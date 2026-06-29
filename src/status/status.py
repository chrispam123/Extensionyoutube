# -*- coding: utf-8 -*-
import json
import os

import boto3
from aws_lambda_powertools import Logger

from shared.auth import decode_nocturne_jwt
from shared.responses import cors_response, get_cors_headers

logger = Logger()

# Inicialización de Clientes
ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")
if not ENDPOINT_URL or not ENDPOINT_URL.strip():
    ENDPOINT_URL = None

dynamo = boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL)
ssm = boto3.client("ssm", endpoint_url=ENDPOINT_URL)
s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL)  # <--- NUEVO CLIENTE


def lambda_handler(event, context):
    # 1. Guardia CORS
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return {"statusCode": 200, "headers": get_cors_headers()}

    table = dynamo.Table(os.getenv("DYNAMODB_TABLE"))

    try:
        # 2. VALIDACIÓN DE IDENTIDAD
        auth_header = event.get("headers", {}).get("authorization", "")
        token = auth_header.split(" ")[1] if " " in auth_header else ""
        jwt_secret = ssm.get_parameter(
            Name="/extension/auth/jwt_secret", WithDecryption=True
        )["Parameter"]["Value"]

        decoded = decode_nocturne_jwt(token, jwt_secret)
        user_id = decoded["sub"]

        # 3. CONSULTA DE ESTADO
        job_id = event.get("pathParameters", {}).get("jobId")
        response = table.get_item(Key={"PK": f"USER#{user_id}", "SK": f"JOB#{job_id}"})
        item = response.get("Item")

        if not item:
            return cors_response(404, {"error": "Trabajo no encontrado"})

        status = item.get("status")

        # 4. CONTRATO DE RESPUESTA BASE
        data = {
            "jobId": item.get("jobId"),
            "status": status,
            "doneCount": int(item.get("doneCount", 0)),
            "type": item.get("type"),  # <--- ESTA ES LA LÍNEA CRÍTICA QUE FALTABA
            "updatedAt": item.get("updatedAt"),
        }

        # =====================================================================
        # 5. LÓGICA DE ENTREGA: GENERAR URL SI ESTÁ TERMINADO
        # =====================================================================
        if status == "DONE":
            logger.info(f"🎁 Job {job_id} finalizado. Generando URL de descarga...")
            bucket_name = os.getenv("S3_BUCKET")
            s3_key = f"exports/{user_id}/{job_id}.json"

            download_url = s3.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": bucket_name, "Key": s3_key},
                ExpiresIn=300,  # El usuario tiene 5 minutos para iniciar la descarga
            )
            data["downloadUrl"] = download_url
        # =====================================================================

        return cors_response(200, data)

    except Exception as e:
        logger.exception("Error en Lambda Status")
        return cors_response(500, {"error": "Internal Server Error"})
