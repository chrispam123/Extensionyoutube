# -*- coding: utf-8 -*-
import httpx
from aws_lambda_powertools import Logger

logger = Logger()


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    """
    Habla con Google OAuth2 para obtener un nuevo Access Token.
    """
    url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    try:
        # Usamos un timeout estricto de 5 segundos para no colgar la Lambda
        with httpx.Client(timeout=5.0) as client:
            response = client.post(url, data=data)

        if response.status_code != 200:
            logger.error(f"Error de Google OAuth: {response.text}")
            response.raise_for_status()

        return response.json()["access_token"]

    except Exception as e:
        logger.exception("Fallo crítico al refrescar el token de Google")
        raise e
