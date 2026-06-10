# -*- coding: utf-8 -*-
"""
Test: Bala trazadora
Description: Simulates the full flow using real YouTube JSON format.
"""

import boto3
import json
import os
import base64
from dotenv import load_dotenv

# Cargar variables del .env
load_dotenv()

ENDPOINT = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
REGION = os.getenv("AWS_REGION", "us-east-1")

# BUCKET = "nocturne-s3-uploads-local"
# TABLE = "nocturne-dynamo-jobs-local"
# QUEUE_NAME = "nocturne-sqs-main-local"
# 3. Nombres de Recursos (Leídos del entorno, NO hardcodeados)
# Usamos el nombre de la variable del .env como fuente de verdad
TABLE = os.getenv("DYNAMODB_TABLE")
BUCKET = os.getenv("S3_BUCKET")
QUEUE_NAME = os.getenv("SQS_QUEUE_NAME")
# Verificación de seguridad: Si falta alguna variable, el script debe "Gritar"
if not all([TABLE, BUCKET, QUEUE_NAME]):
    print("❌ ERROR: Faltan variables de entorno. Revisa tu archivo .env")
    exit(1)
# 4. Inicialización de Clientes
s3 = boto3.client("s3", endpoint_url=ENDPOINT, region_name=REGION)
sqs = boto3.client("sqs", endpoint_url=ENDPOINT, region_name=REGION)
dynamo = boto3.client("dynamodb", endpoint_url=ENDPOINT, region_name=REGION)
# 1. Añadimos el cliente de KMS se va probar el encriptado
kms = boto3.client("kms", endpoint_url=ENDPOINT, region_name=REGION)
KMS_KEY_ALIAS = os.getenv("KMS_KEY_ALIAS")
# Clientes
# s3 = boto3.client("s3", endpoint_url=ENDPOINT)
# sqs = boto3.client("sqs", endpoint_url=ENDPOINT)
# dynamo = boto3.client("dynamodb", endpoint_url=ENDPOINT)


def fire():
    job_id = "job-yt-001"
    user_id = "user-serudda"
    # CIFRADO PREVIO: Simulamos que el Dispatcher cifra el token
    print(f"--- Cifrando token para el usuario {user_id} ---")
    token_plano = "google_refresh_token_fake_12345"
    kms_response = kms.encrypt(
        KeyId=KMS_KEY_ALIAS, Plaintext=token_plano.encode("utf-8")
    )

    # Convertimos los bytes cifrados a Base64 para guardarlos en DynamoDB
    ciphertext_b64 = base64.b64encode(kms_response["CiphertextBlob"]).decode("utf-8")

    # 3. GUARDAR EN DYNAMODB
    print(f"--- Creando Job {job_id} con token cifrado ---")
    dynamo.put_item(
        TableName=TABLE,
        Item={
            "jobId": {"S": job_id},
            "status": {"S": "PENDING"},
            "userId": {"S": user_id},
            "encryptedRefreshToken": {"S": ciphertext_b64},  # <--- EL TESORO GUARDADO
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
