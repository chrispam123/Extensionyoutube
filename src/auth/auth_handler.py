# -*- coding: utf-8 -*-
import base64
import datetime
import json
import os

import boto3
import httpx
from boto3.dynamodb.types import TypeSerializer
from aws_lambda_powertools import Logger, Tracer
from botocore.exceptions import ClientError

from shared.auth import create_nocturne_jwt
from shared.responses import cors_response, get_cors_headers

logger = Logger()
tracer = Tracer()


def _get_endpoint_url():
    raw = os.getenv("AWS_ENDPOINT_URL")
    return raw if raw and raw.strip() else None


def _get_region():
    return os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION", "us-east-1")


def _get_ssm():
    return boto3.client(
        "ssm", region_name=_get_region(), endpoint_url=_get_endpoint_url()
    )


def _get_kms():
    return boto3.client(
        "kms", region_name=_get_region(), endpoint_url=_get_endpoint_url()
    )


def _get_dynamo():
    return boto3.resource(
        "dynamodb", region_name=_get_region(), endpoint_url=_get_endpoint_url()
    )


def _get_ssm_parameter(ssm_client, name: str, with_decryption: bool = False) -> str:
    response = ssm_client.get_parameter(Name=name, WithDecryption=with_decryption)
    return response["Parameter"]["Value"]


def _save_or_update_user_profile(
    table,
    kms_client,
    user_id: str,
    email: str,
    refresh_token: str | None,
    platform: str,
):
    """
    Persiste o actualiza atómicamente el perfil del usuario según la plataforma.
    Para ANDROID: PK=USER#{sub}, SK=PROFILE#ANDROID.
    Para CHROME: PK=USER#{sub}, SK=PROFILE#CHROME y espejo SK=PROFILE (para retrocompatibilidad).
    Si Google no devuelve refresh_token (usuario recurrente),
    se preserva el encryptedRefreshToken previo sin sobrescribirlo ni borrarlo.
    """
    now_iso = datetime.datetime.now(datetime.UTC).isoformat()

    keys_to_update = []
    if platform == "ANDROID":
        keys_to_update.append({"PK": f"USER#{user_id}", "SK": "PROFILE#ANDROID"})
    else:
        # Chrome: perfil específico y espejo de compatibilidad
        keys_to_update.append({"PK": f"USER#{user_id}", "SK": "PROFILE#CHROME"})
        keys_to_update.append({"PK": f"USER#{user_id}", "SK": "PROFILE"})

    expression_attribute_names = {
        "#email": "email",
        "#platform": "platform",
        "#updatedAt": "updatedAt",
    }
    update_expression = (
        "SET #email = :email, #platform = :platform, #updatedAt = :updatedAt"
    )
    expression_values = {
        ":email": email,
        ":platform": platform,
        ":updatedAt": now_iso,
    }

    if refresh_token:
        kms_resp = kms_client.encrypt(
            KeyId=os.getenv("KMS_KEY_ALIAS"),
            Plaintext=refresh_token.encode("utf-8"),
        )
        encrypted_rt = base64.b64encode(kms_resp["CiphertextBlob"]).decode("utf-8")
        update_expression = (
            "SET #email = :email, #platform = :platform, "
            "#encryptedRefreshToken = :rt, #updatedAt = :updatedAt"
        )
        expression_attribute_names["#encryptedRefreshToken"] = "encryptedRefreshToken"
        expression_values[":rt"] = encrypted_rt

    if len(keys_to_update) == 1:
        table.update_item(
            Key=keys_to_update[0],
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_values,
        )
    else:
        serializer = TypeSerializer()
        serialized_values = {
            name: serializer.serialize(value)
            for name, value in expression_values.items()
        }
        try:
            table.meta.client.transact_write_items(
                TransactItems=[
                    {
                        "Update": {
                            "TableName": table.name,
                            "Key": {
                                name: serializer.serialize(value)
                                for name, value in key.items()
                            },
                            "UpdateExpression": update_expression,
                            "ExpressionAttributeNames": dict(
                                expression_attribute_names
                            ),
                            "ExpressionAttributeValues": dict(serialized_values),
                        }
                    }
                    for key in keys_to_update
                ]
            )
        except ClientError as error:
            error_details = error.response.get("Error", {})
            cancellation_reasons = error.response.get("CancellationReasons", [])
            cancellation_codes = [
                reason.get("Code")
                for reason in cancellation_reasons
                if reason.get("Code")
            ]
            request_id = error.response.get("ResponseMetadata", {}).get(
                "RequestId", "unknown"
            )
            logger.error(
                "Chrome profile transaction failed: "
                f"error_code={error_details.get('Code', 'unknown')}, "
                f"cancellation_codes={cancellation_codes or ['unavailable']}, "
                f"request_id={request_id}"
            )
            raise


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return {"statusCode": 200, "headers": get_cors_headers()}

    ssm_client = _get_ssm()
    kms_client = _get_kms()
    dynamo_resource = _get_dynamo()
    table = dynamo_resource.Table(os.getenv("DYNAMODB_TABLE"))

    try:
        body = json.loads(event.get("body", "{}")) if event.get("body") else {}
    except Exception:
        body = {}

    raw_path = (
        event.get("rawPath")
        or event.get("path")
        or event.get("resource")
        or event.get("requestContext", {}).get("http", {}).get("path")
        or ""
    )
    route_key = (
        event.get("routeKey") or event.get("requestContext", {}).get("routeKey") or ""
    )
    is_mobile_flow = (
        "mobile" in raw_path
        or "mobile" in route_key
        or ("code_verifier" in body if isinstance(body, dict) else False)
    )

    try:
        auth_code = body.get("code")

        if not auth_code:
            return cors_response(400, {"error": "Missing authorization code"})

        env = os.getenv("ENVIRONMENT", "develop")
        prefix = f"/extension/{env}" if env else "/extension"

        jwt_secret = _get_ssm_parameter(
            ssm_client, f"{prefix}/auth/jwt_secret", with_decryption=True
        )

        if is_mobile_flow:
            logger.info("📥 Iniciando flujo de autenticación móvil (PKCE)")
            code_verifier = body.get("code_verifier")
            redirect_uri = body.get("redirect_uri")

            if not code_verifier:
                logger.warning("❌ Falta code_verifier para PKCE en login móvil")
                return cors_response(400, {"error": "Missing code_verifier for PKCE"})

            if not redirect_uri:
                logger.warning("❌ Falta redirect_uri en login móvil")
                return cors_response(400, {"error": "Missing redirect_uri"})

            # Obtener client_id y redirect_uri móvil específicos desde SSM (fuente canónica)
            client_id = _get_ssm_parameter(
                ssm_client, f"{prefix}/mobile/google/client_id"
            )
            expected_redirect_uri = _get_ssm_parameter(
                ssm_client, f"{prefix}/mobile/google/redirect_uri"
            )

            if not client_id or client_id == "REPLACE_ME":
                logger.error("❌ SSM parameter mobile/google/client_id no configurado")
                return cors_response(
                    500,
                    {"error": "Server configuration error: client_id is REPLACE_ME"},
                )

            if not expected_redirect_uri or expected_redirect_uri == "REPLACE_ME":
                logger.error(
                    "❌ SSM parameter mobile/google/redirect_uri no configurado"
                )
                return cors_response(
                    500,
                    {"error": "Server configuration error: redirect_uri is REPLACE_ME"},
                )

            if redirect_uri != expected_redirect_uri:
                logger.warning("❌ redirect_uri no autorizada en flujo móvil")
                return cors_response(
                    400, {"error": "Invalid or disallowed redirect_uri"}
                )

            token_data = {
                "code": auth_code,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
                "grant_type": "authorization_code",
            }

            try:
                client_secret = _get_ssm_parameter(
                    ssm_client,
                    f"{prefix}/mobile/google/client_secret",
                    with_decryption=True,
                )
                if client_secret:
                    token_data["client_secret"] = client_secret
            except Exception:
                pass

        else:
            # Flujo de extensión Chrome intacto
            logger.info("📥 Iniciando flujo de autenticación de extensión Chrome")
            client_id = _get_ssm_parameter(ssm_client, f"{prefix}/google/client_id")
            client_secret = _get_ssm_parameter(
                ssm_client, f"{prefix}/google/client_secret", with_decryption=True
            )
            redirect_uri = f"https://{os.getenv('EXTENSION_ID')}.chromiumapp.org/"

            token_data = {
                "code": auth_code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            }

        # Intercambio de tokens con Google OAuth2
        response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data=token_data,
        )

        if response.status_code != 200:
            provider_error = None
            try:
                parsed = response.json()
                if isinstance(parsed, dict):
                    provider_error = parsed.get("error")
            except Exception:
                pass

            if provider_error is None:
                provider_error = "unknown"

            logger.error(
                f"❌ Fallo en Google OAuth: status_code={response.status_code}, "
                f"provider_error={provider_error}"
            )
            return cors_response(401, {"error": "Google Auth Failed"})

        tokens = response.json()
        refresh_token = tokens.get("refresh_token")

        # Identificar Usuario con Google userinfo
        user_info = httpx.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        ).json()
        user_id = user_info["sub"]
        email = user_info.get("email")

        platform = "ANDROID" if is_mobile_flow else "CHROME"

        # Cifrado y Persistencia Atómica en DynamoDB (separado por plataforma, preserva refresh token)
        _save_or_update_user_profile(
            table, kms_client, user_id, email, refresh_token, platform
        )

        # Generar JWT interno de Nocturne con la plataforma asignada por el backend
        nocturne_jwt = create_nocturne_jwt(
            user_id, email, jwt_secret, platform=platform
        )

        logger.info(f"✅ Login exitoso para {email} (plataforma: {platform})")
        return cors_response(200, {"token": nocturne_jwt, "user": email})

    except Exception:
        logger.exception("🔥 Error crítico en λ-Auth")
        return cors_response(500, {"error": "Internal Server Error"})
