# -*- coding: utf-8 -*-
"""
Project: Nocturne Backend
Component: Resumer Lambda
Purpose: Scan for PAUSED_QUOTA jobs and re-enqueue them into SQS.
"""

import datetime
import json
import os
import time

import boto3
from aws_lambda_powertools import Logger

logger = Logger()

# Inicialización de Clientes (Warm Start)
ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")
if not ENDPOINT_URL or not ENDPOINT_URL.strip():
    ENDPOINT_URL = None

dynamo = boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL)
sqs = boto3.client("sqs", endpoint_url=ENDPOINT_URL)


def lambda_handler(event, context):
    table = dynamo.Table(os.getenv("DYNAMODB_TABLE"))
    queue_url = os.getenv("SQS_QUEUE_URL")

    logger.info("⏰ Iniciando ciclo de resurrección de trabajos...")

    try:
        # 1. CONSULTA AL GSI (StatusIndex)
        # Buscamos solo los que están en PAUSED_QUOTA
        response = table.query(
            IndexName="StatusIndex",
            KeyConditionExpression="#s = :val",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":val": "PAUSED_QUOTA"},
        )

        jobs_to_resume = response.get("Items", [])
        logger.info(f"🔎 Se han encontrado {len(jobs_to_resume)} trabajos pausados.")

        for job in jobs_to_resume:
            job_id = job["jobId"]
            user_id = job["userId"]

            logger.info(f"💉 Reanimando Job {job_id} para el usuario {user_id}...")

            # 2. RE-ENCOLAR EN SQS
            sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(
                    {
                        "jobId": job_id,
                        "userId": user_id,
                        "type": job.get("type", "EXPORT"),
                    }
                ),
            )

            # 3. ACTUALIZAR ESTADO A PENDING
            # Lo sacamos de PAUSED_QUOTA para que no lo vuelva a pillar el Resumer
            table.update_item(
                Key={"PK": job["PK"], "SK": job["SK"]},
                UpdateExpression="SET #s = :new_status, updatedAt = :now",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":new_status": "PENDING",
                    ":now": datetime.datetime.now(datetime.UTC).isoformat(),
                },
            )

            # 4. LÓGICA DE GOTEO (Throttling)
            # Esperamos 1 segundo antes del siguiente para no saturar
            time.sleep(1)

        logger.info("✅ Ciclo de resurrección completado.")
        return {"resumed_count": len(jobs_to_resume)}

    except Exception as e:
        logger.exception("🔥 Error en el proceso de resurrección")
        raise e
