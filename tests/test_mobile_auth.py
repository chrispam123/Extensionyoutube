# -*- coding: utf-8 -*-
import json
import boto3
import pytest
from moto import mock_aws
from src.auth.auth_handler import lambda_handler


class MockContext:
    def __init__(self):
        self.function_name = "extension-auth-develop"
        self.memory_limit_in_mb = "256"
        self.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:extension-auth-develop"
        self.aws_request_id = "test-request-auth-123"


def _create_mock_aws_infrastructure():
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    ssm = boto3.client("ssm", region_name="us-east-1")
    kms = boto3.client("kms", region_name="us-east-1")

    # 1. Crear KMS Key y Alias
    key = kms.create_key(Description="Token key")
    kms.create_alias(AliasName="alias/extension/token-key-develop", TargetKeyId=key["KeyMetadata"]["KeyId"])

    # 2. Crear Tabla DynamoDB
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

    # 3. Crear Parámetros SSM en develop
    ssm.put_parameter(
        Name="/extension/develop/google/client_id",
        Value="ext-client-id.apps.googleusercontent.com",
        Type="String",
    )
    ssm.put_parameter(
        Name="/extension/develop/google/client_secret",
        Value="ext-client-secret",
        Type="SecureString",
    )
    ssm.put_parameter(
        Name="/extension/develop/mobile/google/client_id",
        Value="937802721244-0tovqumfb5lpgmqgo1r6kq1fposcstst.apps.googleusercontent.com",
        Type="String",
    )
    ssm.put_parameter(
        Name="/extension/develop/auth/jwt_secret",
        Value="super-secret-jwt-signing-key-12345",
        Type="SecureString",
    )

    return {"table": table, "ssm": ssm, "kms": kms}


@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "develop")
    monkeypatch.setenv("DYNAMODB_TABLE", "extension-dynamo-jobs-develop")
    monkeypatch.setenv("KMS_KEY_ALIAS", "alias/extension/token-key-develop")
    monkeypatch.setenv("EXTENSION_ID", "abcdefghijklmnop")


@mock_aws
def test_mobile_auth_success(aws_env, mocker):
    infra = _create_mock_aws_infrastructure()
    table = infra["table"]
    mobile_redirect = "com.googleusercontent.apps.937802721244-0tovqumfb5lpgmqgo1r6kq1fposcstst:/oauth2callback"

    # Mock llamadas httpx hacia Google
    mock_post = mocker.patch("httpx.post")
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "access_token": "mock-access-token",
        "refresh_token": "mock-new-refresh-token",
    }

    mock_get = mocker.patch("httpx.get")
    mock_get.return_value.json.return_value = {
        "sub": "google-user-sub-999",
        "email": "user@gmail.com",
    }

    event = {
        "rawPath": "/auth/mobile/login",
        "requestContext": {"http": {"method": "POST", "path": "/auth/mobile/login"}},
        "body": json.dumps({
            "code": "valid-auth-code",
            "code_verifier": "valid-pkce-verifier-123",
            "redirect_uri": mobile_redirect,
        }),
    }

    response = lambda_handler(event, MockContext())
    assert response["statusCode"] == 200

    body = json.loads(response["body"])
    assert "token" in body
    assert body["user"] == "user@gmail.com"

    # Validar que se envió code_verifier a Google
    mock_post.assert_called_once()
    sent_data = mock_post.call_args[1]["data"]
    assert sent_data["code_verifier"] == "valid-pkce-verifier-123"
    assert sent_data["redirect_uri"] == mobile_redirect

    # Validar persistencia en DynamoDB
    item = table.get_item(Key={"PK": "USER#google-user-sub-999", "SK": "PROFILE"}).get("Item")
    assert item is not None
    assert item["email"] == "user@gmail.com"
    assert "encryptedRefreshToken" in item


@mock_aws
def test_mobile_auth_missing_code_verifier(aws_env):
    _create_mock_aws_infrastructure()
    mobile_redirect = "com.googleusercontent.apps.937802721244-0tovqumfb5lpgmqgo1r6kq1fposcstst:/oauth2callback"
    event = {
        "rawPath": "/auth/mobile/login",
        "requestContext": {"http": {"method": "POST", "path": "/auth/mobile/login"}},
        "body": json.dumps({
            "code": "valid-auth-code",
            "redirect_uri": mobile_redirect,
        }),
    }

    response = lambda_handler(event, MockContext())
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "Missing code_verifier" in body["error"]


@mock_aws
def test_mobile_auth_disallowed_redirect_uri(aws_env):
    _create_mock_aws_infrastructure()
    # Intentar usar el redirect de Chrome en el endpoint móvil debe ser rechazado
    event = {
        "rawPath": "/auth/mobile/login",
        "requestContext": {"http": {"method": "POST", "path": "/auth/mobile/login"}},
        "body": json.dumps({
            "code": "valid-auth-code",
            "code_verifier": "valid-pkce-verifier-123",
            "redirect_uri": "https://abcdefghijklmnop.chromiumapp.org/",
        }),
    }

    response = lambda_handler(event, MockContext())
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "Invalid or disallowed redirect_uri" in body["error"]


@mock_aws
def test_mobile_auth_preserves_existing_refresh_token_when_none_returned(aws_env, mocker):
    infra = _create_mock_aws_infrastructure()
    table = infra["table"]
    mobile_redirect = "com.googleusercontent.apps.937802721244-0tovqumfb5lpgmqgo1r6kq1fposcstst:/oauth2callback"

    # Pre-crear perfil con refresh token previo
    table.put_item(
        Item={
            "PK": "USER#google-user-sub-999",
            "SK": "PROFILE",
            "email": "user@gmail.com",
            "encryptedRefreshToken": "PREVIOUS_ENCRYPTED_TOKEN",
            "updatedAt": "2026-01-01T00:00:00Z",
        }
    )

    # Google no devuelve refresh_token (usuario recurrente)
    mock_post = mocker.patch("httpx.post")
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "access_token": "mock-access-token",
    }

    mock_get = mocker.patch("httpx.get")
    mock_get.return_value.json.return_value = {
        "sub": "google-user-sub-999",
        "email": "user@gmail.com",
    }

    event = {
        "rawPath": "/auth/mobile/login",
        "requestContext": {"http": {"method": "POST", "path": "/auth/mobile/login"}},
        "body": json.dumps({
            "code": "valid-auth-code",
            "code_verifier": "valid-pkce-verifier-123",
            "redirect_uri": mobile_redirect,
        }),
    }

    response = lambda_handler(event, MockContext())
    assert response["statusCode"] == 200

    # Verificar que el encryptedRefreshToken NO fue borrado ni sobrescrito
    item = table.get_item(Key={"PK": "USER#google-user-sub-999", "SK": "PROFILE"})["Item"]
    assert item["encryptedRefreshToken"] == "PREVIOUS_ENCRYPTED_TOKEN"


@mock_aws
def test_mobile_auth_replaces_refresh_token_when_new_returned(aws_env, mocker):
    infra = _create_mock_aws_infrastructure()
    table = infra["table"]
    mobile_redirect = "com.googleusercontent.apps.937802721244-0tovqumfb5lpgmqgo1r6kq1fposcstst:/oauth2callback"

    # Pre-crear perfil con token previo
    table.put_item(
        Item={
            "PK": "USER#google-user-sub-999",
            "SK": "PROFILE",
            "email": "user@gmail.com",
            "encryptedRefreshToken": "OLD_TOKEN",
            "updatedAt": "2026-01-01T00:00:00Z",
        }
    )

    mock_post = mocker.patch("httpx.post")
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "access_token": "mock-access-token",
        "refresh_token": "NEW_RAW_REFRESH_TOKEN",
    }

    mock_get = mocker.patch("httpx.get")
    mock_get.return_value.json.return_value = {
        "sub": "google-user-sub-999",
        "email": "user@gmail.com",
    }

    event = {
        "rawPath": "/auth/mobile/login",
        "requestContext": {"http": {"method": "POST", "path": "/auth/mobile/login"}},
        "body": json.dumps({
            "code": "valid-auth-code",
            "code_verifier": "valid-pkce-verifier-123",
            "redirect_uri": mobile_redirect,
        }),
    }

    response = lambda_handler(event, MockContext())
    assert response["statusCode"] == 200

    item = table.get_item(Key={"PK": "USER#google-user-sub-999", "SK": "PROFILE"})["Item"]
    assert item["encryptedRefreshToken"] != "OLD_TOKEN"


@mock_aws
def test_mobile_auth_google_token_exchange_failure(aws_env, mocker):
    _create_mock_aws_infrastructure()
    mobile_redirect = "com.googleusercontent.apps.937802721244-0tovqumfb5lpgmqgo1r6kq1fposcstst:/oauth2callback"

    mock_post = mocker.patch("httpx.post")
    mock_post.return_value.status_code = 400
    mock_post.return_value.text = "invalid_grant"

    event = {
        "rawPath": "/auth/mobile/login",
        "requestContext": {"http": {"method": "POST", "path": "/auth/mobile/login"}},
        "body": json.dumps({
            "code": "invalid-auth-code",
            "code_verifier": "valid-pkce-verifier-123",
            "redirect_uri": mobile_redirect,
        }),
    }

    response = lambda_handler(event, MockContext())
    assert response["statusCode"] == 401
    body = json.loads(response["body"])
    assert body["error"] == "Google Auth Failed"


@mock_aws
def test_mobile_auth_missing_code(aws_env):
    _create_mock_aws_infrastructure()
    mobile_redirect = "com.googleusercontent.apps.937802721244-0tovqumfb5lpgmqgo1r6kq1fposcstst:/oauth2callback"
    event = {
        "rawPath": "/auth/mobile/login",
        "requestContext": {"http": {"method": "POST", "path": "/auth/mobile/login"}},
        "body": json.dumps({
            "code_verifier": "valid-pkce-verifier-123",
            "redirect_uri": mobile_redirect,
        }),
    }

    response = lambda_handler(event, MockContext())
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "Missing authorization code" in body["error"]


@mock_aws
def test_extension_auth_regression(aws_env, mocker):
    _create_mock_aws_infrastructure()
    mock_post = mocker.patch("httpx.post")
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "access_token": "mock-access-token",
        "refresh_token": "mock-ext-refresh-token",
    }

    mock_get = mocker.patch("httpx.get")
    mock_get.return_value.json.return_value = {
        "sub": "google-ext-user",
        "email": "ext_user@gmail.com",
    }

    event = {
        "rawPath": "/auth/login",
        "requestContext": {"http": {"method": "POST", "path": "/auth/login"}},
        "body": json.dumps({
            "code": "ext-auth-code",
        }),
    }

    response = lambda_handler(event, MockContext())
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert "token" in body
    assert body["user"] == "ext_user@gmail.com"

    # Verificar que la extensión usó su redirect de Chromium
    sent_data = mock_post.call_args[1]["data"]
    assert sent_data["redirect_uri"] == "https://abcdefghijklmnop.chromiumapp.org/"
    assert "code_verifier" not in sent_data
