# -*- coding: utf-8 -*-
import json
import os
import boto3
from aws_lambda_powertools import Logger
from shared.responses import cors_response, get_cors_headers
from shared.auth import decode_nocturne_jwt

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
        # 2. EXTRAER IDENTIDAD (Con Log de Perito)
        auth_header = event.get("headers", {}).get("authorization", "")

        # LOG CRÍTICO: Ver qué llega exactamente
        logger.info(f"DEBUG: Auth Header recibido: '{auth_header}'")

        if not auth_header or "Bearer " not in auth_header:
            logger.warning("Petición sin cabecera Bearer")
            return cors_response(401, {"error": "No autorizado: Falta Token"})

        token = auth_header.split(" ")[1]
        logger.info(f"DEBUG: Token extraído (longitud): {len(token)}")

        # 3. VALIDACIÓN
        jwt_secret = ssm.get_parameter(
            Name="/extension/auth/jwt_secret", WithDecryption=True
        )["Parameter"]["Value"]

        try:
            decoded = decode_nocturne_jwt(token, jwt_secret)
            user_id = decoded["sub"]
        except Exception as jwt_err:
            logger.error(f"Error decodificando JWT: {str(jwt_err)}")
            return cors_response(401, {"error": f"Token inválido: {str(jwt_err)}"})

        # 4. CONSULTA DYNAMODB
        job_id = event.get("pathParameters", {}).get("jobId")
        logger.info(f"🔍 Buscando Job {job_id} para usuario {user_id}")

        response = table.get_item(Key={"PK": f"USER#{user_id}", "SK": f"JOB#{job_id}"})
        item = response.get("Item")

        if not item:
            return cors_response(404, {"error": "Trabajo no encontrado"})

        return cors_response(
            200,
            {
                "jobId": item.get("jobId"),
                "status": item.get("status"),
                "doneCount": int(item.get("doneCount", 0)),
            },
        )

    except Exception as e:
        logger.exception("Error no controlado en Status")
        return cors_response(500, {"error": "Internal Server Error"})
