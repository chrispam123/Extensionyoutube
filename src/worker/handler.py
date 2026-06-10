# -*- coding: utf-8 -*-
"""
Project: Nocturne Backend
Component: Worker Lambda (Tracer Bullet + KMS Identity)
License: Proprietary
"""

import json
import os
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger, Tracer

# NUEVO: Importación de la capa compartida de seguridad
# Esto permite que la lógica de cifrado sea reutilizable por otras Lambdas
from shared.security import decrypt_token

# 1. Configuración de Observabilidad
logger = Logger()
tracer = Tracer()

# 2. Inicialización de Clientes (Fuera del handler para reutilizar conexión - Warm Start)
ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")
s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL)
dynamo = boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL)

# NUEVO: Inicialización del cliente de KMS fuera del handler
# Principio DevOps: Reutilizamos la conexión TCP/SSL para reducir latencia en ejecuciones calientes
kms_client = boto3.client("kms", endpoint_url=ENDPOINT_URL)


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    """
    Procesa mensajes de SQS, descifra tokens de usuario y gestiona suscripciones.
    """
    table_name = os.getenv("DYNAMODB_TABLE", "extension-dynamo-jobs-local")
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

            # =================================================================
            # NUEVO: LÓGICA DE DESCIFRADO DE TOKEN (ÉPICA IDENTIDAD)
            # =================================================================
            # 1. Recuperamos el registro completo de DynamoDB para obtener el token cifrado
            job_response = table.get_item(Key={"jobId": job_id})
            job_item = job_response.get("Item", {})
            encrypted_token = job_item.get("encryptedRefreshToken")

            if not encrypted_token:
                logger.warning(
                    f"No se encontró 'encryptedRefreshToken' para el Job {job_id}. Saltando descifrado."
                )
            else:
                # 2. Desciframos usando la utilidad compartida.
                # Inyectamos el kms_client global para máxima eficiencia.
                token_real = decrypt_token(kms_client, encrypted_token)

                # LOG DE SEGURIDAD: Solo mostramos un rastro parcial (4 caracteres) para auditoría.
                # Principio DevOps: Nunca exponer secretos completos en logs.
                logger.info(
                    f"Token descifrado con éxito. (Prefix: {token_real[:4]}...)"
                )
            # =================================================================

            # C. Simular descarga del Bunker (S3)
            bucket = os.getenv("S3_BUCKET")
            key = f"uploads/{user_id}/{job_id}.json"

            logger.info(f"Descargando datos desde s3://{bucket}/{key}")
            response = s3.get_object(Bucket=bucket, Key=key)
            raw_data = response["Body"].read().decode("utf-8")
            data = json.loads(raw_data)

            ## CORRECCIÓN: El JSON de YouTube es una lista directa
            if isinstance(data, list):
                items_count = len(data)
            else:
                items_count = 0
            logger.info(f"Bala Trazadora exitosa: {items_count} canales encontrados.")

            # E. Finalizar (En la bala trazadora lo marcamos como DONE)
            table.update_item(
                Key={"jobId": job_id},
                UpdateExpression="SET #s = :val",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":val": "DONE"},
            )

        except Exception as e:
            logger.exception(f"Fallo crítico en el Worker: {str(e)}")
            raise e

    return {"status": "processed"}
