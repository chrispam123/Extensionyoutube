# -*- coding: utf-8 -*-
import base64
import datetime
import json
import os

import boto3
import httpx
from aws_lambda_powertools import Logger, Tracer

from shared.auth import create_nocturne_jwt
from shared.responses import cors_response, get_cors_headers

logger = Logger()
tracer = Tracer()

# Clientes AWS
ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")
if not ENDPOINT_URL or not ENDPOINT_URL.strip():
    ENDPOINT_URL = None

ssm = boto3.client("ssm", endpoint_url=ENDPOINT_URL)
kms = boto3.client("kms", endpoint_url=ENDPOINT_URL)
dynamo = boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL)


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return {"statusCode": 200, "headers": get_cors_headers()}

    table = dynamo.Table(os.getenv("DYNAMODB_TABLE"))

    try:
        body = json.loads(event.get("body", "{}"))
        auth_code = body.get("code")
        logger.info("📥 Recibido código de autorización de Google")

        # 1. Recuperar Secretos
        logger.info("🔍 Consultando secretos en SSM...")
        env = os.getenv("ENVIRONMENT", "")
        prefix = f"/extension/{env}" if env else "/extension"
        client_id = ssm.get_parameter(Name=f"{prefix}/google/client_id")["Parameter"][
            "Value"
        ]
        client_secret = ssm.get_parameter(
            Name=f"{prefix}/google/client_secret", WithDecryption=True
        )["Parameter"]["Value"]
        jwt_secret = ssm.get_parameter(
            Name=f"{prefix}/auth/jwt_secret", WithDecryption=True
        )["Parameter"]["Value"]

        # 2. Intercambio de Tokens
        logger.info("📡 Intercambiando código por tokens en Google OAuth2...")
        redirect_uri = f"https://{os.getenv('EXTENSION_ID')}.chromiumapp.org/"

        response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": auth_code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )

        if response.status_code != 200:
            logger.error(f"❌ Fallo en Google OAuth: {response.text}")
            return cors_response(401, {"error": "Google Auth Failed"})

        tokens = response.json()
        refresh_token = tokens.get("refresh_token")

        # 3. Identificar Usuario
        logger.info("👤 Recuperando información del perfil del usuario...")
        user_info = httpx.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        ).json()
        user_id = user_info["sub"]
        email = user_info.get("email")

        # 4. Cifrado y Persistencia
        if refresh_token:
            logger.info(f"🔐 Cifrando Refresh Token con KMS para el usuario {email}...")
            kms_resp = kms.encrypt(
                KeyId=os.getenv("KMS_KEY_ALIAS"),
                Plaintext=refresh_token.encode("utf-8"),
            )
            encrypted_rt = base64.b64encode(kms_resp["CiphertextBlob"]).decode("utf-8")

            logger.info("💾 Guardando perfil en DynamoDB...")
            table.put_item(
                Item={
                    "PK": f"USER#{user_id}",
                    "SK": "PROFILE",
                    "email": email,
                    "encryptedRefreshToken": encrypted_rt,
                    "updatedAt": datetime.datetime.now(datetime.UTC).isoformat(),
                }
            )
        else:
            logger.info("ℹ️ Google no envió Refresh Token (el usuario ya existía).")

        # 5. Generar JWT de Nocturne
        logger.info("🎫 Emitiendo Pasaporte Nocturne (JWT)...")
        nocturne_jwt = create_nocturne_jwt(user_id, email, jwt_secret)

        logger.info(f"✅ Login exitoso para {email}")
        return cors_response(200, {"token": nocturne_jwt, "user": email})

    except Exception as e:
        logger.exception("🔥 Error crítico en λ-Auth")
        return cors_response(500, {"error": "Internal Server Error"})
