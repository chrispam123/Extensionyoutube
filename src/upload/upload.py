# -*- coding: utf-8 -*-
"""
Project: Nocturne Backend
Component: Initiator (Upload) Lambda
Purpose: Create Job in DynamoDB and either provide S3 URL (Import) or trigger SQS (Export).
"""

import json
import os
import uuid

import boto3
from aws_lambda_powertools import Logger, Tracer
from botocore.config import Config

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
    table_name = os.getenv("DYNAMODB_TABLE")
    bucket_name = os.getenv("S3_BUCKET")
    work_queue_url = os.getenv("SQS_QUEUE_URL")
    table = dynamo.Table(table_name)

    try:
        # 2. PARSEO DE ENTRADA
        body = json.loads(event.get("body", "{}"))
        user_id = body.get("userId")
        job_type = body.get("type", "IMPORT").upper()  # IMPORT o EXPORT

        if not user_id:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "userId es obligatorio"}),
            }

        # 3. GENERACIÓN DE IDENTIDAD
        job_id = str(uuid.uuid4())
        # El estado inicial depende del tipo de trabajo
        initial_status = "INITIALIZING" if job_type == "IMPORT" else "PENDING"

        logger.info(f"Creando Job {job_id} de tipo {job_type} para usuario {user_id}")

        # 4. REGISTRO EN DYNAMODB (Primero el mapa)
        table.put_item(
            Item={
                "jobId": job_id,
                "userId": user_id,
                "type": job_type,
                "status": initial_status,
                "doneCount": 0,
                "totalItems": 0,
                "createdAt": (
                    int(context.aws_request_id.split("-")[0], 16)
                    if not ENDPOINT_URL
                    else 123456789
                ),
            }
        )

        # 5. BIFURCACIÓN DE LÓGICA
        response_body = {"jobId": job_id, "type": job_type}

        if job_type == "IMPORT":
            # CASO IMPORTACIÓN: Generar URL para que el usuario suba el archivo
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
            response_body["uploadUrl"] = upload_url
            logger.info(f"Presigned URL generada para Job {job_id}")

        else:
            # CASO EXPORTACIÓN: Avisar al Worker directamente
            sqs.send_message(
                QueueUrl=work_queue_url,
                MessageBody=json.dumps({"jobId": job_id, "userId": user_id}),
            )
            logger.info(f"Mensaje de exportación enviado a SQS para Job {job_id}")

        # 6. RESPUESTA EXITOSA
        return {
            "statusCode": 201,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(response_body),
        }

    except Exception as e:
        logger.exception(f"Fallo al iniciar Job")
        return {"statusCode": 500, "body": json.dumps({"error": "Error interno"})}
