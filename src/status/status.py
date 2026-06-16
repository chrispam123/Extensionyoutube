# -*- coding: utf-8 -*-
"""
Project: Nocturne Backend
Component: Status Lambda
"""

import json
import os

import boto3
from aws_lambda_powertools import Logger

# IMPORTANTE: Usamos nuestra capa compartida para mantener el estándar CORS
from shared.responses import cors_response, get_cors_headers

logger = Logger()

# 1. Inicialización de Clientes (Warm Start)
ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")
if not ENDPOINT_URL or not ENDPOINT_URL.strip():
    ENDPOINT_URL = None

dynamo = boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL)


def lambda_handler(event, context):
    # --- BLOQUE DE SEGURIDAD: MANEJO DE PREFLIGHT (OPTIONS) ---
    # Principio de Eficiencia: Respondemos antes de inicializar lógica pesada
    method = event.get("requestContext", {}).get("http", {}).get("method")
    if method == "OPTIONS":
        return {"statusCode": 200, "headers": get_cors_headers()}

    # --- LÓGICA DE NEGOCIO ---
    table_name = os.getenv("DYNAMODB_TABLE")
    table = dynamo.Table(table_name)

    path_params = event.get("pathParameters", {})
    job_id = path_params.get("jobId")

    if not job_id:
        return cors_response(400, {"error": "Falta el parámetro jobId"})

    try:
        response = table.get_item(Key={"jobId": job_id})
        item = response.get("Item")

        if not item:
            # Principio de Veracidad HTTP
            return cors_response(404, {"error": f"Job {job_id} no encontrado"})

        # 3. CONTRATO DE RESPUESTA (Filtrado de seguridad)
        data = {
            "jobId": item.get("jobId"),
            "status": item.get("status"),
            "doneCount": int(item.get("doneCount", 0)),
            "totalItems": int(item.get("totalItems", 0)),
            "updatedAt": item.get("updatedAt"),
        }

        # Usamos la utilidad para devolver el JSON con cabeceras dinámicas
        return cors_response(200, data)

    except Exception as e:
        logger.exception(f"Error al consultar estado del Job {job_id}")
        return cors_response(500, {"error": "Internal Server Error"})
