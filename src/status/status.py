# -*- coding: utf-8 -*-
"""
Project: Nocturne Backend
Component: Status Lambda
Purpose: Provide real-time job progress to the frontend via API Gateway.
"""

import json
import os

import boto3
from aws_lambda_powertools import Logger

logger = Logger()

# Inicialización de Clientes (Warm Start)
ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")
# Limpieza de endpoint para paridad Local/Cloud
if not ENDPOINT_URL or not ENDPOINT_URL.strip():
    ENDPOINT_URL = None

dynamo = boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL)


def lambda_handler(event, context):
    table_name = os.getenv("DYNAMODB_TABLE")
    table = dynamo.Table(table_name)

    # 1. EXTRAER EL ID DE LA URL
    # API Gateway pone los parámetros de ruta en 'pathParameters'
    path_params = event.get("pathParameters", {})
    job_id = path_params.get("jobId")

    if not job_id:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Falta el parámetro jobId"}),
        }

    try:
        # 2. CONSULTA QUIRÚRGICA
        response = table.get_item(Key={"jobId": job_id})
        item = response.get("Item")

        if not item:
            # Principio de Veracidad HTTP: 404 si no existe
            return {
                "statusCode": 404,
                "body": json.dumps({"error": f"Job {job_id} no encontrado"}),
            }

        # 3. CONTRATO DE RESPUESTA (Solo lo necesario)
        # No devolvemos tokens ni datos sensibles
        data = {
            "jobId": item.get("jobId"),
            "status": item.get("status"),
            "doneCount": int(item.get("doneCount", 0)),
            "totalItems": int(item.get("totalItems", 0)),
            "updatedAt": item.get("updatedAt"),
        }

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",  # Doble seguridad para CORS
            },
            "body": json.dumps(data),
        }

    except Exception as e:
        logger.exception(f"Error al consultar estado del Job {job_id}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal Server Error"}),
        }
