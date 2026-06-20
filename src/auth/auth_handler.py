# -*- coding: utf-8 -*-
import base64  # Asegúrate de que este también esté si usas base64.b64encode
import datetime  # <--- ESTA ES LA PIEZA QUE FALTA
import json
import os

import boto3
import httpx
from aws_lambda_powertools import Logger, Tracer
from shared.auth import create_nocturne_jwt
from shared.responses import cors_response, get_cors_headers
from shared.security import decrypt_token  # Aunque aquí usaremos encrypt

logger = Logger()
tracer = Tracer()

# Clientes AWS
ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")
if not ENDPOINT_URL or not ENDPOINT_URL.strip():
    ENDPOINT_URL = None

ssm = boto3.client("ssm", endpoint_url=ENDPOINT_URL)
kms = boto3.client("kms", endpoint_url=ENDPOINT_URL)
dynamo = boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL)


def lambda_handler(event, context):
    # 1. Guardia CORS (OPTIONS)
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return {"statusCode": 200, "headers": get_cors_headers()}

    table = dynamo.Table(os.getenv("DYNAMODB_TABLE"))

    try:
        # 2. Obtener código de Google desde el Frontend
        body = json.loads(event.get("body", "{}"))
        auth_code = body.get("code")

        # 3. Recuperar Secretos Maestros (SSM)
        # En un entorno real, aquí usaríamos caché como en el Worker
        client_id = ssm.get_parameter(Name="/extension/google/client_id")["Parameter"][
            "Value"
        ]
        client_secret = ssm.get_parameter(
            Name="/extension/google/client_secret", WithDecryption=True
        )["Parameter"]["Value"]
        jwt_secret = ssm.get_parameter(
            Name="/extension/auth/jwt_secret", WithDecryption=True
        )["Parameter"]["Value"]

        # 4. Intercambio con Google OAuth2
        token_url = "https://oauth2.googleapis.com/token"
        # El redirect_uri debe coincidir EXACTAMENTE con el de Google Console
        redirect_uri = f"https://{os.getenv('EXTENSION_ID')}.chromiumapp.org/"

        response = httpx.post(
            token_url,
            data={
                "code": auth_code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )

        if response.status_code != 200:
            logger.error(f"Google Auth Error: {response.text}")
            return cors_response(401, {"error": "Código de Google inválido"})

        tokens = response.json()
        refresh_token = tokens.get("refresh_token")
        # Google solo envía el refresh_token la PRIMERA vez que el usuario acepta

        # 5. Obtener info del usuario (ID de Google)
        # Usamos el access_token que acabamos de recibir para saber quién es
        user_info = httpx.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        ).json()
        user_id = user_info["sub"]
        email = user_info.get("email")

        # 6. Cifrar y Guardar (Búnker)
        if refresh_token:
            kms_resp = kms.encrypt(
                KeyId=os.getenv("KMS_KEY_ALIAS"),
                Plaintext=refresh_token.encode("utf-8"),
            )
            import base64

            encrypted_rt = base64.b64encode(kms_resp["CiphertextBlob"]).decode("utf-8")

            # Guardamos en DynamoDB (Single Table Design)
            table.put_item(
                Item={
                    "PK": f"USER#{user_id}",
                    "SK": "PROFILE",
                    "email": email,
                    "encryptedRefreshToken": encrypted_rt,
                    "updatedAt": datetime.datetime.utcnow().isoformat(),
                }
            )

        # 7. Emitir Pasaporte Nocturne
        nocturne_jwt = create_nocturne_jwt(user_id, email, jwt_secret)

        return cors_response(200, {"token": nocturne_jwt, "user": email})

    except Exception as e:
        logger.exception("Fallo en el proceso de autenticación")
        return cors_response(500, {"error": "Internal Server Error"})
