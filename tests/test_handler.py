# -*- coding: utf-8 -*-
import json

import boto3
import pytest
from moto import mock_aws
from src.worker.handler import lambda_handler


# 1. El "Doble de Acción" para el contexto de AWS
class MockContext:
    def __init__(self):
        self.function_name = "extension-worker-local"
        self.memory_limit_in_mb = "128"
        self.invoked_function_arn = (
            "arn:aws:lambda:us-east-1:000000000000:function:extension-worker-local"
        )
        self.aws_request_id = "test-request-id"


@mock_aws
def test_handler_success(monkeypatch, mocker):
    # ---------------------------------------------------------
    # 1. ARRANGE: Configuración de entorno
    # ---------------------------------------------------------
    monkeypatch.setenv("DYNAMODB_TABLE", "extension-dynamo-table-local")
    monkeypatch.setenv("S3_BUCKET", "extension-s3-uploads-local")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("SQS_QUEUE_URL", "http://fake-queue-url")

    # --- MOCKS DE LÓGICA (Evitamos llamadas reales) ---
    mocker.patch("src.worker.handler.decrypt_token", return_value="fake-token")
    mocker.patch("src.worker.handler.refresh_access_token", return_value="fake-access")
    mock_yt = mocker.patch("src.worker.handler.YouTubeClient")
    mock_yt.return_value.get_subscriptions.return_value = {
        "items": [{"id": "c1"}],
        "nextPageToken": None,
    }

    # 2. RECURSOS AWS (Moto)
    s3 = boto3.client("s3", region_name="us-east-1")
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    ssm = boto3.client("ssm", region_name="us-east-1")

    # Preparar SSM (Simulamos que los secretos ya están ahí)
    ssm.put_parameter(Name="/extension/google/client_id", Value="fake", Type="String")
    ssm.put_parameter(
        Name="/extension/google/client_secret", Value="fake", Type="String"
    )

    # Preparar S3
    s3.create_bucket(Bucket="extension-s3-uploads-local")

    # [CONTRATO]: Tabla con PK y SK
    table = dynamodb.create_table(
        TableName="extension-dynamo-table-local",
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
        ],
        ProvisionedThroughput={"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
    )

    user_id = "user-123"
    job_id = "job-abc"

    # [ESCENARIO]: Creamos el PROFILE del usuario
    table.put_item(
        Item={
            "PK": f"USER#{user_id}",
            "SK": "PROFILE",
            "encryptedRefreshToken": "ZmFrZS10b2tlbg==",  # Base64 de 'fake-token'
        }
    )

    # [ESCENARIO]: Creamos el registro del JOB
    table.put_item(
        Item={
            "PK": f"USER#{user_id}",
            "SK": f"JOB#{job_id}",
            "jobId": job_id,
            "userId": user_id,
            "status": "PENDING",
            "type": "EXPORT",
        }
    )

    # 3. EL EVENTO (Lo que enviaría SQS)
    event = {"Records": [{"body": json.dumps({"jobId": job_id, "userId": user_id})}]}

    # ---------------------------------------------------------
    # 2. ACT: Ejecutar la Lambda
    # ---------------------------------------------------------
    response = lambda_handler(event, MockContext())

    # ---------------------------------------------------------
    # 3. ASSERT: Verificar éxito
    # ---------------------------------------------------------
    assert response["status"] == "processed"

    # Verificamos que el JOB (y no el PROFILE) se actualizó a DONE
    job_item = table.get_item(Key={"PK": f"USER#{user_id}", "SK": f"JOB#{job_id}"})[
        "Item"
    ]

    assert job_item["status"] == "DONE"
    assert "updatedAt" in job_item
