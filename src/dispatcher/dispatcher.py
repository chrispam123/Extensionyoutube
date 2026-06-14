# -*- coding: utf-8 -*-
"""
Project: Nocturne Backend
Component: Dispatcher Lambda
Purpose: Translate S3 events into Work messages for the Worker.
"""

import json
import os

import boto3
from aws_lambda_powertools import Logger, Tracer

logger = Logger()
tracer = Tracer()

# Inicialización de Clientes (Warm Start)
ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")

# BIEN (Interfaz de alto nivel)
dynamo = boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL)
sqs = boto3.client("sqs", endpoint_url=ENDPOINT_URL)


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    table_name = os.getenv("DYNAMODB_TABLE")
    table = dynamo.Table(table_name)  # type: ignore
    work_queue_url = os.getenv("SQS_QUEUE_URL")

    for record in event.get("Records", []):
        try:
            # 1. DESENVOLVER EL SOBRE (SQS -> S3 Event)
            sqs_body = json.loads(record["body"])

            # S3 envía una lista de registros dentro del mensaje de SQS
            s3_records = sqs_body.get("Records", [])
            if not s3_records:
                logger.warning("Mensaje de SQS no contiene registros de S3. Ignorando.")
                continue

            for s3_rec in s3_records:
                s3_key = s3_rec["s3"]["object"]["key"]
                # Formato esperado: uploads/{userId}/{jobId}.json
                parts = s3_key.split("/")

                if len(parts) < 3:
                    logger.error(
                        f"Ruta de S3 inválida: {s3_key}. No cumple el contrato."
                    )
                    continue  # Tu decisión: Ignorar y borrar de SQS

                user_id = parts[1]
                job_id = parts[2].replace(".json", "")

                logger.info(f"Validando Job {job_id} para usuario {user_id}")

                # 2. ACTUALIZAR ESTADO (Cerebro)
                # Solo pasamos a PENDING si el Job existe
                try:
                    table.update_item(
                        Key={"jobId": job_id},
                        UpdateExpression="SET #s = :val",
                        ExpressionAttributeNames={"#s": "status"},
                        ExpressionAttributeValues={":val": "PENDING"},
                        ConditionExpression="attribute_exists(jobId)",
                    )
                except Exception as e:
                    logger.error(
                        f"No se pudo actualizar el Job {job_id} en DynamoDB: {str(e)}"
                    )
                    continue

                # 3. ENCOLAR TRABAJO (Hacia el Worker)
                sqs.send_message(
                    QueueUrl=work_queue_url,
                    MessageBody=json.dumps({"jobId": job_id, "userId": user_id}),
                )
                logger.info(f"Job {job_id} enviado a la cola de trabajo con éxito.")

        except Exception as e:
            logger.exception(f"Error procesando registro de ingesta: {str(e)}")
            # Aquí sí lanzamos excepción para que SQS reintente si es un fallo técnico
            raise e

    return {"status": "dispatched"}
