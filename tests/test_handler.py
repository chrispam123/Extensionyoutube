# -*- coding: utf-8 -*-
import boto3
import pytest
import json
from moto import mock_aws
from src.worker.handler import lambda_handler


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
    # 1. ARRANGE: Configuración de entorno
    monkeypatch.setenv("S3_BUCKET", "extension-s3-uploads-local")
    monkeypatch.setenv("DYNAMODB_TABLE", "extension-dynamo-jobs-local")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("SQS_QUEUE_URL", "http://fake-queue-url")

    # --- MOCKS DE LÓGICA (Evitamos KMS y Google) ---
    # Parcheamos el descifrado para que devuelva un token plano directamente
    mocker.patch(
        "src.worker.handler.decrypt_token", return_value="token-real-desbloqueado"
    )

    # Parcheamos el refresco de Google
    mocker.patch(
        "src.worker.handler.refresh_access_token", return_value="fake-access-token"
    )

    # Parcheamos el cliente de YouTube
    mock_yt = mocker.patch("src.worker.handler.YouTubeClient")
    mock_yt.return_value.get_subscriptions.return_value = {
        "items": [{"id": "chan1"}],
        "nextPageToken": None,
    }

    # 2. RECURSOS AWS (Moto)
    s3 = boto3.client("s3", region_name="us-east-1")
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    ssm = boto3.client("ssm", region_name="us-east-1")

    ssm.put_parameter(Name="/extension/google/client_id", Value="fake", Type="String")
    ssm.put_parameter(
        Name="/extension/google/client_secret", Value="fake", Type="String"
    )
    s3.create_bucket(Bucket="extension-s3-uploads-local")

    table = dynamodb.create_table(
        TableName="extension-dynamo-jobs-local",
        KeySchema=[{"AttributeName": "jobId", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "jobId", "AttributeType": "S"}],
        ProvisionedThroughput={"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
    )

    job_id = "job-1"
    table.put_item(
        Item={
            "jobId": job_id,
            "status": "PENDING",
            "encryptedRefreshToken": "cualquier-cosa-no-importa-el-mock-lo-saltara",
        }
    )

    s3.put_object(
        Bucket="extension-s3-uploads-local",
        Key=f"uploads/user-1/{job_id}.json",
        Body=json.dumps([{"id": "chan1"}]),
    )

    # 3. ACT: Ejecutar la Lambda
    event = {"Records": [{"body": json.dumps({"jobId": job_id, "userId": "user-1"})}]}
    response = lambda_handler(event, MockContext())

    # 4. ASSERT: Verificar éxito
    assert response["status"] == "processed"
    item = table.get_item(Key={"jobId": job_id})["Item"]
    assert item["status"] == "DONE"
