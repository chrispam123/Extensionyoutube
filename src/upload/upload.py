# -*- coding: utf-8 -*-
"""
Project: Nocturne Backend
Component: Initiator (Upload) Lambda
"""

import json
import os
import uuid

import boto3
from aws_lambda_powertools import Logger, Tracer
from botocore.config import Config

# IMPORTANTE: Capa compartida para consistencia en la API
from shared.responses import cors_response, get_cors_headers

logger = Logger()
tracer = Tracer()

# 1. Inicialización de Clientes (Warm Start)
RAW_ENDPOINT = os.getenv("AWS_ENDPOINT_URL")
ENDPOINT_URL = RAW_ENDPOINT if RAW_ENDPOINT and RAW_ENDPOINT.strip() else None

# Configuración para S3 Presigned URLs (Path style para LocalStack)
s3_config = Config(s3={"addressing_style": "path"}) if ENDPOINT_URL else Config()

s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL, config=s3_config)
dynamo = boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL)
sqs = boto3.client("sqs", endpoint_url=ENDPOINT_URL)


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    # --- BLOQUE DE SEGURIDAD: MANEJO DE PREFLIGHT (OPTIONS) ---
    method = event.get("requestContext", {}).get("http", {}).get("method")
    if method == "OPTIONS":
        return {"statusCode": 200, "headers": get_cors_headers()}

    # --- LÓGICA DE NEGOCIO ---
    table_name = os.getenv("DYNAMODB_TABLE")
    bucket_name = os.getenv("S3_BUCKET")
    work_queue_url = os.getenv("SQS_QUEUE_URL")
    table = dynamo.Table(table_name)

    try:
        body = json.loads(event.get("body", "{}"))
        user_id = body.get("userId")
        job_type = body.get("type", "IMPORT").upper()

        if not user_id:
            return cors_response(400, {"error": "userId es obligatorio"})

        # 2. GENERACIÓN DE IDENTIDAD Y ESTADO INICIAL
        job_id = str(uuid.uuid4())
        initial_status = "INITIALIZING" if job_type == "IMPORT" else "PENDING"

        logger.info(f"Iniciando Job {job_id} ({job_type}) para {user_id}")

        # 3. REGISTRO EN DYNAMODB (El Notario)
        table.put_item(
            Item={
                "jobId": job_id,
                "userId": user_id,
                "type": job_type,
                "status": initial_status,
                "doneCount": 0,
                "totalItems": 0,
                "createdAt": int(context.aws_request_id.split("-")[0], 16)
                if not ENDPOINT_URL
                else 123456789,
            }
        )

        # 4. BIFURCACIÓN DE FLUJO
        response_data = {"jobId": job_id, "type": job_type}

        if job_type == "IMPORT":
            # Generar contrato de subida a S3
            s3_key = f"uploads/{user_id}/{job_id}.json"
            upload_url = s3.generate_presigned_url(
                ClientMethod="put_object",
                Params={
                    "Bucket": bucket_name,
                    "Key": s3_key,
                    "ContentType": "application/json",
                },
                ExpiresIn=300,
            )
            response_data["uploadUrl"] = upload_url
        else:
            # Iniciar exportación directa vía SQS
            sqs.send_message(
                QueueUrl=work_queue_url,
                MessageBody=json.dumps({"jobId": job_id, "userId": user_id}),
            )

        return cors_response(201, response_data)

    except Exception as e:
        logger.exception(f"Error al crear Job")
        return cors_response(500, {"error": "No se pudo procesar la solicitud"})
