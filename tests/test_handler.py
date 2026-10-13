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

    mocker.patch("src.worker.handler.dynamo", dynamodb)
    mocker.patch("src.worker.handler.s3", s3)
    mocker.patch("src.worker.handler.ssm", ssm)

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


@mock_aws
def test_handler_android_success(monkeypatch, mocker):
    from src.worker.handler import cached_secrets

    cached_secrets["client_id"] = None
    cached_secrets["client_secret"] = None
    cached_secrets["mobile_client_id"] = None

    monkeypatch.setenv("DYNAMODB_TABLE", "extension-dynamo-table-local")
    monkeypatch.setenv("S3_BUCKET", "extension-s3-uploads-local")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("SQS_QUEUE_URL", "http://fake-queue-url")

    mocker.patch("src.worker.handler.decrypt_token", return_value="fake-token")
    mock_refresh = mocker.patch(
        "src.worker.handler.refresh_access_token", return_value="fake-access"
    )

    mock_yt = mocker.patch("src.worker.handler.YouTubeClient")
    mock_yt.return_value.get_subscriptions.return_value = {
        "items": [
            {
                "id": "s1",
                "snippet": {
                    "title": "Android Channel",
                    "resourceId": {"channelId": "UC999"},
                    "thumbnails": {"default": {"url": "http://img.jpg"}},
                },
            }
        ],
        "nextPageToken": None,
    }

    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    s3 = boto3.client("s3", region_name="us-east-1")
    ssm = boto3.client("ssm", region_name="us-east-1")

    mocker.patch("src.worker.handler.dynamo", dynamodb)
    mocker.patch("src.worker.handler.s3", s3)
    mocker.patch("src.worker.handler.ssm", ssm)

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

    s3.create_bucket(Bucket="extension-s3-uploads-local")

    ssm.put_parameter(
        Name="/extension/mobile/google/client_id",
        Value="fake-mobile-client-id",
        Type="String",
    )

    user_id = "user-android-123"
    job_id = "job-android-abc"

    table.put_item(
        Item={
            "PK": f"USER#{user_id}",
            "SK": "PROFILE#ANDROID",
            "encryptedRefreshToken": "ZmFrZS10b2tlbg==",
            "platform": "ANDROID",
        }
    )

    table.put_item(
        Item={
            "PK": f"USER#{user_id}",
            "SK": f"JOB#{job_id}",
            "jobId": job_id,
            "userId": user_id,
            "credentialType": "ANDROID",
            "status": "PENDING",
            "type": "EXPORT",
            "options": {"channels": True, "playlists": False},
            "doneCount": 0,
            "failedCount": 0,
        }
    )

    event = {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "jobId": job_id,
                        "userId": user_id,
                        "credentialType": "ANDROID",
                    }
                )
            }
        ]
    }

    response = lambda_handler(event, MockContext())
    assert response["status"] == "processed"

    # Verificar que para ANDROID se invoca sin client_secret
    mock_refresh.assert_called_once_with("fake-mobile-client-id", None, "fake-token")

    job_item = table.get_item(Key={"PK": f"USER#{user_id}", "SK": f"JOB#{job_id}"})[
        "Item"
    ]
    assert job_item["status"] == "DONE"
    assert int(job_item["doneCount"]) == 1


@mock_aws
def test_handler_permanent_auth_failure_marks_job_failed(monkeypatch, mocker):
    import httpx
    from src.worker.handler import cached_secrets

    cached_secrets["client_id"] = None
    cached_secrets["client_secret"] = None
    cached_secrets["mobile_client_id"] = None

    monkeypatch.setenv("DYNAMODB_TABLE", "extension-dynamo-table-local")
    monkeypatch.setenv("S3_BUCKET", "extension-s3-uploads-local")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("SQS_QUEUE_URL", "http://fake-queue-url")

    mocker.patch("src.worker.handler.decrypt_token", return_value="fake-token")

    req = httpx.Request("POST", "https://oauth2.googleapis.com/token")
    resp = httpx.Response(400, request=req, text='{"error": "invalid_grant"}')
    mocker.patch(
        "src.worker.handler.refresh_access_token",
        side_effect=httpx.HTTPStatusError("invalid_grant", request=req, response=resp),
    )

    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    s3 = boto3.client("s3", region_name="us-east-1")
    ssm = boto3.client("ssm", region_name="us-east-1")

    mocker.patch("src.worker.handler.dynamo", dynamodb)
    mocker.patch("src.worker.handler.s3", s3)
    mocker.patch("src.worker.handler.ssm", ssm)

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

    ssm.put_parameter(
        Name="/extension/mobile/google/client_id",
        Value="fake-mobile-client-id",
        Type="String",
    )

    user_id = "user-failed-123"
    job_id = "job-failed-abc"

    table.put_item(
        Item={
            "PK": f"USER#{user_id}",
            "SK": "PROFILE#ANDROID",
            "encryptedRefreshToken": "ZmFrZS10b2tlbg==",
            "platform": "ANDROID",
        }
    )

    table.put_item(
        Item={
            "PK": f"USER#{user_id}",
            "SK": f"JOB#{job_id}",
            "jobId": job_id,
            "userId": user_id,
            "credentialType": "ANDROID",
            "status": "PENDING",
            "type": "EXPORT",
            "options": {"channels": True, "playlists": False},
            "doneCount": 0,
            "failedCount": 0,
        }
    )

    event = {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "jobId": job_id,
                        "userId": user_id,
                        "credentialType": "ANDROID",
                    }
                )
            }
        ]
    }

    # ACT: no debe relanzar la excepción para evitar ciclo infinito en SQS
    response = lambda_handler(event, MockContext())
    assert response["status"] == "processed"

    # ASSERT: el Job debe quedar marcado como FAILED en DynamoDB con mensaje explicativo
    job_item = table.get_item(Key={"PK": f"USER#{user_id}", "SK": f"JOB#{job_id}"})[
        "Item"
    ]
    assert job_item["status"] == "FAILED"
    assert "errorMessage" in job_item
    assert "inicia sesión" in job_item["errorMessage"]


@mock_aws
def test_handler_transient_error_re_raises_for_sqs_retry(monkeypatch, mocker):
    import httpx
    from src.worker.handler import cached_secrets

    cached_secrets["client_id"] = None
    cached_secrets["client_secret"] = None
    cached_secrets["mobile_client_id"] = None

    monkeypatch.setenv("DYNAMODB_TABLE", "extension-dynamo-table-local")
    monkeypatch.setenv("S3_BUCKET", "extension-s3-uploads-local")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("SQS_QUEUE_URL", "http://fake-queue-url")

    mocker.patch("src.worker.handler.decrypt_token", return_value="fake-token")

    req = httpx.Request("POST", "https://oauth2.googleapis.com/token")
    mocker.patch(
        "src.worker.handler.refresh_access_token",
        side_effect=httpx.ConnectTimeout("Connection timed out", request=req),
    )

    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    ssm = boto3.client("ssm", region_name="us-east-1")

    mocker.patch("src.worker.handler.dynamo", dynamodb)
    mocker.patch("src.worker.handler.ssm", ssm)

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

    ssm.put_parameter(
        Name="/extension/mobile/google/client_id",
        Value="fake-mobile-client-id",
        Type="String",
    )

    user_id = "user-transient-123"
    job_id = "job-transient-abc"

    table.put_item(
        Item={
            "PK": f"USER#{user_id}",
            "SK": "PROFILE#ANDROID",
            "encryptedRefreshToken": "ZmFrZS10b2tlbg==",
            "platform": "ANDROID",
        }
    )

    table.put_item(
        Item={
            "PK": f"USER#{user_id}",
            "SK": f"JOB#{job_id}",
            "jobId": job_id,
            "userId": user_id,
            "credentialType": "ANDROID",
            "status": "PENDING",
            "type": "EXPORT",
            "options": {"channels": True, "playlists": False},
            "doneCount": 0,
            "failedCount": 0,
        }
    )

    event = {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "jobId": job_id,
                        "userId": user_id,
                        "credentialType": "ANDROID",
                    }
                )
            }
        ]
    }

    # ACT & ASSERT: Debe re-lanzar la excepción para que SQS reintente
    with pytest.raises(httpx.ConnectTimeout):
        lambda_handler(event, MockContext())
