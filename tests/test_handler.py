# -*- coding: utf-8 -*-
import boto3
import pytest
import json
from moto import mock_aws
from src.worker.handler import lambda_handler


# 1. El "Doble de Acción" para el contexto de AWS
class MockContext:
    def __init__(self):
        self.function_name = "extension-worker-local"
        self.memory_limit_in_mb = "256"
        self.invoked_function_arn = (
            "arn:aws:lambda:us-east-1:380894354766:function:extension-worker-develop"
        )
        self.aws_request_id = "test-request-id-123"


@mock_aws
def test_handler_success(monkeypatch, mocker):
    # ---------------------------------------------------------
    # 1. ARRANGE: Preparar el escenario (Single Table Design)
    # ---------------------------------------------------------

    # A. Variables de Entorno
    monkeypatch.setenv("DYNAMODB_TABLE", "extension-dynamo-table-local")
    monkeypatch.setenv("S3_BUCKET", "extension-s3-uploads-local")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("SQS_QUEUE_URL", "http://fake-queue-url")

    # B. Mocks de Lógica (Evitamos llamadas reales a Google/KMS/YouTube)
    mocker.patch("src.worker.handler.decrypt_token", return_value="fake-token")
    mocker.patch("src.worker.handler.refresh_access_token", return_value="fake-access")

    mock_yt = mocker.patch("src.worker.handler.YouTubeClient")
    # Simulamos que YouTube devuelve 1 canal
    mock_yt.return_value.get_subscriptions.return_value = {
        "items": [
            {
                "id": "s1",
                "snippet": {
                    "title": "Test Channel",
                    "resourceId": {"channelId": "UC123"},
                    "thumbnails": {"default": {"url": "http://img.jpg"}},
                },
            }
        ],
        "nextPageToken": None,
    }

    # C. Recursos AWS en Memoria (Moto)
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    s3 = boto3.client("s3", region_name="us-east-1")
    ssm = boto3.client("ssm", region_name="us-east-1")

    # Crear Tabla con PK y SK
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

    # Crear Bucket
    s3.create_bucket(Bucket="extension-s3-uploads-local")

    # Crear Parámetros SSM
    ssm.put_parameter(Name="/extension/google/client_id", Value="fake", Type="String")
    ssm.put_parameter(
        Name="/extension/google/client_secret", Value="fake", Type="String"
    )

    # D. Datos de Prueba (El Escenario de Usuario)
    user_id = "user-123"
    job_id = "job-abc"

    # Item 1: El Perfil (Donde vive el token)
    table.put_item(
        Item={
            "PK": f"USER#{user_id}",
            "SK": "PROFILE",
            "encryptedRefreshToken": "ZmFrZS10b2tlbg==",  # Base64 válido
        }
    )

    # Item 2: El Job (Donde vive el progreso)
    table.put_item(
        Item={
            "PK": f"USER#{user_id}",
            "SK": f"JOB#{job_id}",
            "jobId": job_id,
            "userId": user_id,
            "status": "PENDING",
            "type": "EXPORT",
            "options": {"channels": True, "playlists": False},
            "doneCount": 0,
            "failedCount": 0,
        }
    )

    # E. El Evento de SQS
    event = {"Records": [{"body": json.dumps({"jobId": job_id, "userId": user_id})}]}

    # ---------------------------------------------------------
    # 2. ACT: Ejecutar la lógica
    # ---------------------------------------------------------
    response = lambda_handler(event, MockContext())

    # ---------------------------------------------------------
    # 3. ASSERT: Verificar resultados
    # ---------------------------------------------------------
    assert response["status"] == "processed"

    # Verificamos que el Job se actualizó correctamente
    job_item = table.get_item(Key={"PK": f"USER#{user_id}", "SK": f"JOB#{job_id}"})[
        "Item"
    ]

    assert job_item["status"] == "DONE"
    assert int(job_item["doneCount"]) == 1
    assert "updatedAt" in job_item
