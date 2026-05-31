# -*- coding: utf-8 -*-
"""
Project: Nocturne Backend
Component: Worker Lambda (Tracer Bullet)
License: Proprietary
"""

import json
import os
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger, Tracer

# 1. Configuración de Observabilidad
logger = Logger()
tracer = Tracer()

# 2. Inicialización de Clientes (Fuera del handler para reutilizar conexión)
# Usamos la variable de entorno para decidir si apuntamos a LocalStack o AWS
ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")
s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL)
dynamo = boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL)


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    """
    Procesa mensajes de SQS para exportar/importar suscripciones.
    """
    table_name = os.getenv("DYNAMODB_TABLE", "nocturne-dynamo-jobs-local")
    table = dynamo.Table(table_name)

    for record in event.get("Records", []):
        try:
            # A. Parseo del Mensaje (Claim Check Pattern)
            payload = json.loads(record["body"])
            job_id = payload.get("jobId")
            user_id = payload.get("userId")

            if not job_id or not user_id:
                logger.error("Mensaje mal formado: faltan IDs")
                continue

            logger.info(f"Iniciando procesamiento de Job: {job_id}")

            # B. Actualizar Estado en DynamoDB (Cerebro)
            # Usamos una expresión condicional para asegurar que solo procesamos si está PENDING
            try:
                table.update_item(
                    Key={"jobId": job_id},
                    UpdateExpression="SET #s = :val",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={":val": "RUNNING"},
                    ConditionExpression="attribute_exists(jobId)",
                )
            except ClientError as e:
                if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    logger.warning(f"El Job {job_id} no existe o ya fue procesado.")
                    continue
                raise

            # C. Simular descarga del Bunker (S3)
            bucket = os.getenv("S3_BUCKET")
            key = f"uploads/{user_id}/{job_id}.json"

            logger.info(f"Descargando datos desde s3://{bucket}/{key}")
            response = s3.get_object(Bucket=bucket, Key=key)
            raw_data = response["Body"].read().decode("utf-8")
            data = json.loads(raw_data)

            # D. Simulación de Lógica de Negocio (Aquí iría YouTube después)
            items_count = len(data.get("subscriptions", []))
            logger.info(
                f"Bala Trazadora exitosa: {items_count} suscripciones listas para procesar."
            )

            # E. Finalizar (En la bala trazadora lo marcamos como DONE)
            table.update_item(
                Key={"jobId": job_id},
                UpdateExpression="SET #s = :val",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":val": "DONE"},
            )

        except Exception as e:
            logger.exception(f"Fallo crítico en el Worker: {str(e)}")
            # Al lanzar la excepción, SQS mantendrá el mensaje para reintento
            raise e

    return {"status": "processed"}
