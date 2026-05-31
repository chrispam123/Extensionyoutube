# -*- coding: utf-8 -*-
"""
Test: Bala trazadora
Description: Simulates the full flow using real YouTube JSON format.
"""
import boto3
import json
import os
from dotenv import load_dotenv

# Cargar variables del .env
load_dotenv()

ENDPOINT = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
BUCKET = "nocturne-s3-uploads-local"
TABLE = "nocturne-dynamo-jobs-local"
QUEUE_NAME = "nocturne-sqs-main-local"

# Clientes
s3 = boto3.client("s3", endpoint_url=ENDPOINT)
sqs = boto3.client("sqs", endpoint_url=ENDPOINT)
dynamo = boto3.client("dynamodb", endpoint_url=ENDPOINT)


def fire():
    job_id = "job-yt-001"
    user_id = "user-serudda"

    # 1. Crear registro en DynamoDB
    print(f"--- Creando Job {job_id} en DynamoDB ---")
    dynamo.put_item(
        TableName=TABLE,
        Item={
            "jobId": {"S": job_id},
            "status": {"S": "PENDING"},
            "userId": {"S": user_id},
        },
    )

    # 2. Subir JSON con tu formato real a S3
    youtube_data = [
        {
            "id": "ADOWjAF8ESgE3HO46vzR6grTL2glOjfpAkpVNGbb2-s",
            "title": "Serudda",
            "channelId": "UCiF653G_a4nAj169A6ORyrw",
            "type": "CHANNEL",
        }
    ]

    s3_key = f"uploads/{user_id}/{job_id}.json"
    print(f"--- Subiendo JSON a S3: {s3_key} ---")
    s3.put_object(Bucket=BUCKET, Key=s3_key, Body=json.dumps(youtube_data))

    # 3. Enviar mensaje a SQS
    print(f"--- Enviando mensaje a SQS ---")
    queue_url = sqs.get_queue_url(QueueName=QUEUE_NAME)["QueueUrl"]
    sqs.send_message(
        QueueUrl=queue_url, MessageBody=json.dumps({"jobId": job_id, "userId": user_id})
    )

    print("\n✅ Bala disparada con éxito.")
    print(f"Próximo paso: Revisa los logs de la Lambda o el estado en DynamoDB.")


if __name__ == "__main__":
    fire()
