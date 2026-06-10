# -*- coding: utf-8 -*-
# errores de cuota y token acceso expirado
import httpx
from shared.exceptions import QuotaExceededError, InvalidTokenError


class YouTubeClient:
    def __init__(self, access_token: str):
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.headers = {"Authorization": f"Bearer {access_token}"}

    def get_subscriptions(self, max_results=50, page_token=None):
        """
        Obtiene la lista de suscripciones del usuario.
        """
        url = f"{self.base_url}/subscriptions"
        params = {"part": "snippet", "mine": "true", "maxResults": max_results}
        if page_token:
            params["pageToken"] = page_token

        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, headers=self.headers, params=params)

        if response.status_code == 200:
            return response.json()

        # --- MAPEO DE ERRORES (EL SENSOR) ---
        error_data = response.json().get("error", {})
        error_reason = error_data.get("errors", [{}])[0].get("reason")

        if response.status_code == 403 and error_reason == "quotaExceeded":
            raise QuotaExceededError("Límite de cuota de YouTube alcanzado")

        if response.status_code == 401:
            raise InvalidTokenError("El Access Token ha expirado o es inválido")

        response.raise_for_status()
