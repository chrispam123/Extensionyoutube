# -*- coding: utf-8 -*-
import json
import os

import boto3
from aws_lambda_powertools import Logger
from shared.auth import (
    decode_nocturne_jwt,  # <--- NUEVO: Necesitamos validar quién pregunta
)
from shared.responses import cors_response, get_cors_headers

logger = Logger()

# Inicialización de Clientes
ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")
if not ENDPOINT_URL or not ENDPOINT_URL.strip():
    ENDPOINT_URL = None
dynamo = boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL)
ssm = boto3.client("ssm", endpoint_url=ENDPOINT_URL)


def lambda_handler(event, context):
    # 1. Guardia CORS
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return {"statusCode": 200, "headers": get_cors_headers()}

    table = dynamo.Table(os.getenv("DYNAMODB_TABLE"))

    try:
        # 2. EXTRAER IDENTIDAD DEL JWT (Seguridad)
        auth_header = event.get("headers", {}).get("authorization", "")
        token = auth_header.split(" ")[1] if " " in auth_header else ""

        jwt_secret = ssm.get_parameter(
            Name="/extension/auth/jwt_secret", WithDecryption=True
        )["Parameter"]["Value"]
        decoded = decode_nocturne_jwt(token, jwt_secret)
        user_id = decoded["sub"]

        # 3. EXTRAER ID DEL TRABAJO DE LA URL
        job_id = event.get("pathParameters", {}).get("jobId")

        logger.info(f"🔍 Buscando estado del Job {job_id} para el usuario {user_id}")

        # 4. CONSULTA CON EL NUEVO ESQUEMA (PK/SK)
        # Construimos las llaves según el estándar de nuestra Single Table
        response = table.get_item(Key={"PK": f"USER#{user_id}", "SK": f"JOB#{job_id}"})
        item = response.get("Item")

        if not item:
            return cors_response(
                404, {"error": "Trabajo no encontrado o no pertenece a este usuario"}
            )

        # 5. RESPUESTA FILTRADA
        data = {
            "jobId": item.get("jobId"),
            "status": item.get("status"),
            "doneCount": int(item.get("doneCount", 0)),
            "type": item.get("type"),
        }
        return cors_response(200, data)

    except Exception as e:
        logger.exception("Error en Lambda Status")
        return cors_response(
            401 if "jwt" in str(e).lower() else 500,
            {"error": "No autorizado o error interno"},
        )
