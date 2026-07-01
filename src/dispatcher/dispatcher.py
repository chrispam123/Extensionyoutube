# -*- coding: utf-8 -*-
"""
Project: Nocturne Backend
Component: Dispatcher Lambda
"""

import datetime
import json
import os
import time

import boto3
from aws_lambda_powertools import Logger, Tracer

logger = Logger()
tracer = Tracer()

ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")
dynamo = boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL)
sqs = boto3.client("sqs", endpoint_url=ENDPOINT_URL)


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    table_name = os.getenv("DYNAMODB_TABLE")
    table = dynamo.Table(table_name)
    work_queue_url = os.getenv("SQS_QUEUE_URL")

    for record in event.get("Records", []):
        try:
            sqs_body = json.loads(record["body"])

            # Ignorar eventos de prueba de S3
            if sqs_body.get("Event") == "s3:TestEvent":
                continue

            s3_records = sqs_body.get("Records", [])
            for s3_rec in s3_records:
                s3_key = s3_rec["s3"]["object"]["key"]
                parts = s3_key.split("/")

                user_id = parts[1]
                job_id = parts[2].replace(".json", "")

                logger.info(f"Activando Job {job_id} para usuario {user_id}")

                # =============================================================
                # CORRECCIÓN DE ESQUEMA: SINGLE TABLE DESIGN (PK + SK)
                # =============================================================
                # Antes: Key={"jobId": job_id}
                # Ahora: Pasamos la clave compuesta exacta
                try:
                    table.update_item(
                        Key={"PK": f"USER#{user_id}", "SK": f"JOB#{job_id}"},
                        UpdateExpression="SET #s = :val, expiresAt = :ttl, updatedAt = :now",
                        ConditionExpression="attribute_exists(PK) AND #s = :init",
                        ExpressionAttributeNames={"#s": "status"},
                        ExpressionAttributeValues={
                            ":val": "PENDING",
                            ":init": "INITIALIZING",
                            ":ttl": int(time.time()) + (10 * 86400),
                            ":now": datetime.datetime.now(datetime.UTC).isoformat(),
                        },
                    )
                    logger.info(f"Estado cambiado a PENDING para {job_id}")
                except Exception as e:
                    logger.error(f"Fallo al actualizar estado en DB: {str(e)}")
                    continue
                # =============================================================

                # Encolar hacia el Worker
                sqs.send_message(
                    QueueUrl=work_queue_url,
                    MessageBody=json.dumps({"jobId": job_id, "userId": user_id}),
                )

        except Exception as e:
            logger.exception("Error en Dispatcher")
            raise e

    return {"status": "dispatched"}
