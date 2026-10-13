# -*- coding: utf-8 -*-
import json
import boto3
import pytest
from moto import mock_aws

from src.shared.auth import create_nocturne_jwt
import src.upload.upload as upload_module
import src.status.status as status_module


class MockContext:
    def __init__(self):
        self.function_name = "extension-test"
        self.memory_limit_in_mb = "256"
        self.invoked_function_arn = (
            "arn:aws:lambda:us-east-1:123456789012:function:extension-test"
        )
        self.aws_request_id = "test-req-123"


def _setup_mock_env(monkeypatch, mocker):
    monkeypatch.setenv("DYNAMODB_TABLE", "extension-dynamo-jobs-develop")
    monkeypatch.setenv("S3_BUCKET", "extension-s3-uploads-develop")
    monkeypatch.setenv(
        "SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
    )
    monkeypatch.setenv("ENVIRONMENT", "develop")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    s3 = boto3.client("s3", region_name="us-east-1")
    ssm = boto3.client("ssm", region_name="us-east-1")
    sqs = boto3.client("sqs", region_name="us-east-1")

    # Inyectar clientes en módulos
    mocker.patch.object(upload_module, "dynamo", dynamodb)
    mocker.patch.object(upload_module, "s3", s3)
    mocker.patch.object(upload_module, "ssm", ssm)
    mocker.patch.object(upload_module, "sqs", sqs)

    mocker.patch.object(status_module, "dynamo", dynamodb)
    mocker.patch.object(status_module, "s3", s3)
    mocker.patch.object(status_module, "ssm", ssm)

    # Tabla DynamoDB
    table = dynamodb.create_table(
        TableName="extension-dynamo-jobs-develop",
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

    # Bucket S3
    s3.create_bucket(Bucket="extension-s3-uploads-develop")

    # Cola SQS
    sqs.create_queue(QueueName="test-queue")

    # Parámetro JWT Secret
    jwt_secret = "test-jwt-secret-key-32-bytes-long!!"
    ssm.put_parameter(
        Name="/extension/develop/auth/jwt_secret",
        Value=jwt_secret,
        Type="SecureString",
        Overwrite=True,
    )

    return {
        "table": table,
        "s3": s3,
        "ssm": ssm,
        "sqs": sqs,
        "jwt_secret": jwt_secret,
    }


@mock_aws
def test_create_job_rejects_empty_options(monkeypatch, mocker):
    env = _setup_mock_env(monkeypatch, mocker)
    token = create_nocturne_jwt(
        user_id="user-123",
        email="test@example.com",
        secret=env["jwt_secret"],
        platform="ANDROID",
    )

    event = {
        "headers": {"authorization": f"Bearer {token}"},
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps(
            {
                "type": "EXPORT",
                "options": {"channels": False, "playlists": False},
            }
        ),
    }

    response = upload_module.lambda_handler(event, MockContext())
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "error" in body
    assert "Debes seleccionar al menos una opción" in body["error"]


@mock_aws
def test_create_job_accepts_valid_options(monkeypatch, mocker):
    env = _setup_mock_env(monkeypatch, mocker)
    token = create_nocturne_jwt(
        user_id="user-123",
        email="test@example.com",
        secret=env["jwt_secret"],
        platform="ANDROID",
    )

    event = {
        "headers": {"authorization": f"Bearer {token}"},
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps(
            {
                "type": "EXPORT",
                "options": {"channels": True, "playlists": False},
            }
        ),
    }

    response = upload_module.lambda_handler(event, MockContext())
    assert response["statusCode"] == 201
    body = json.loads(response["body"])
    assert "jobId" in body
    assert body["type"] == "EXPORT"


@mock_aws
def test_create_job_import_returns_upload_url_with_content_type(monkeypatch, mocker):
    env = _setup_mock_env(monkeypatch, mocker)
    token = create_nocturne_jwt(
        user_id="user-123",
        email="test@example.com",
        secret=env["jwt_secret"],
        platform="ANDROID",
    )

    event = {
        "headers": {"authorization": f"Bearer {token}"},
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps(
            {
                "type": "IMPORT",
                "options": {"channels": True, "playlists": True},
            }
        ),
    }

    response = upload_module.lambda_handler(event, MockContext())
    assert response["statusCode"] == 201
    body = json.loads(response["body"])
    assert "jobId" in body
    assert body["type"] == "IMPORT"
    assert "uploadUrl" in body
    assert "extension-s3-uploads-develop" in body["uploadUrl"]


@mock_aws
def test_status_export_done_returns_download_url(monkeypatch, mocker):
    env = _setup_mock_env(monkeypatch, mocker)
    table = env["table"]
    user_id = "user-123"
    job_id = "job-export-done"

    table.put_item(
        Item={
            "PK": f"USER#{user_id}",
            "SK": f"JOB#{job_id}",
            "jobId": job_id,
            "userId": user_id,
            "status": "DONE",
            "type": "EXPORT",
            "doneCount": 50,
            "failedCount": 0,
        }
    )

    token = create_nocturne_jwt(
        user_id=user_id,
        email="test@example.com",
        secret=env["jwt_secret"],
        platform="ANDROID",
    )

    event = {
        "headers": {"authorization": f"Bearer {token}"},
        "pathParameters": {"jobId": job_id},
        "requestContext": {"http": {"method": "GET"}},
    }

    response = status_module.lambda_handler(event, MockContext())
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["status"] == "DONE"
    assert body["type"] == "EXPORT"
    assert "downloadUrl" in body
    assert f"exports/{user_id}/{job_id}.json" in body["downloadUrl"]


@mock_aws
def test_status_import_done_does_not_return_download_url(monkeypatch, mocker):
    env = _setup_mock_env(monkeypatch, mocker)
    table = env["table"]
    user_id = "user-123"
    job_id = "job-import-done"

    table.put_item(
        Item={
            "PK": f"USER#{user_id}",
            "SK": f"JOB#{job_id}",
            "jobId": job_id,
            "userId": user_id,
            "status": "DONE",
            "type": "IMPORT",
            "doneCount": 50,
            "failedCount": 0,
        }
    )

    token = create_nocturne_jwt(
        user_id=user_id,
        email="test@example.com",
        secret=env["jwt_secret"],
        platform="ANDROID",
    )

    event = {
        "headers": {"authorization": f"Bearer {token}"},
        "pathParameters": {"jobId": job_id},
        "requestContext": {"http": {"method": "GET"}},
    }

    response = status_module.lambda_handler(event, MockContext())
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["status"] == "DONE"
    assert body["type"] == "IMPORT"
    # IMPORT terminado NO debe tener downloadUrl
    assert "downloadUrl" not in body


@mock_aws
def test_status_import_initializing_returns_fresh_upload_url(monkeypatch, mocker):
    env = _setup_mock_env(monkeypatch, mocker)
    table = env["table"]
    user_id = "user-123"
    job_id = "job-import-initializing"

    table.put_item(
        Item={
            "PK": f"USER#{user_id}",
            "SK": f"JOB#{job_id}",
            "jobId": job_id,
            "userId": user_id,
            "status": "INITIALIZING",
            "type": "IMPORT",
            "doneCount": 0,
            "failedCount": 0,
        }
    )

    token = create_nocturne_jwt(
        user_id=user_id,
        email="test@example.com",
        secret=env["jwt_secret"],
        platform="ANDROID",
    )

    event = {
        "headers": {"authorization": f"Bearer {token}"},
        "pathParameters": {"jobId": job_id},
        "requestContext": {"http": {"method": "GET"}},
    }

    response = status_module.lambda_handler(event, MockContext())
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["status"] == "INITIALIZING"
    assert body["type"] == "IMPORT"
    # IMPORT en INITIALIZING SÍ debe tener uploadUrl renovada
    assert "uploadUrl" in body
    assert f"uploads/{user_id}/{job_id}.json" in body["uploadUrl"]
