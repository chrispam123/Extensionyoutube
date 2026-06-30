# -*- coding: utf-8 -*-
import httpx

from shared.exceptions import InvalidTokenError, QuotaExceededError


class YouTubeClient:
    def __init__(self, access_token: str):
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.headers = {"Authorization": f"Bearer {access_token}"}

    def _handle_response(self, response):
        """Centraliza la detección de errores de cuota y tokens."""
        if response.status_code == 200 or response.status_code == 201:
            return response.json()

        error_data = response.json().get("error", {})
        error_reason = error_data.get("errors", [{}])[0].get("reason")

        if response.status_code == 403 and error_reason == "quotaExceeded":
            raise QuotaExceededError("Límite de cuota de YouTube alcanzado")

        if response.status_code == 401:
            raise InvalidTokenError("Token expirado o inválido")

        response.raise_for_status()

    def get_subscriptions(self, max_results=50, page_token=None):
        url = f"{self.base_url}/subscriptions"
        params = {"part": "snippet", "mine": "true", "maxResults": max_results}
        if page_token:
            params["pageToken"] = page_token

        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, headers=self.headers, params=params)
            return self._handle_response(response)

    def subscribe_to_channel(self, channel_id: str):
        """
        Crea una nueva suscripción en YouTube.
        Coste de cuota: 50 unidades.
        """
        url = f"{self.base_url}/subscriptions"
        params = {"part": "snippet"}
        body = {
            "snippet": {
                "resourceId": {"kind": "youtube#channel", "channelId": channel_id}
            }
        }
        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, headers=self.headers, params=params, json=body)
            return self._handle_response(response)

    def create_playlist(self, title: str, description: str = ""):
        """Crea una carpeta de playlist. Coste: 50 unidades."""
        url = f"{self.base_url}/playlists"
        body = {
            "snippet": {"title": title, "description": description},
            "status": {"privacyStatus": "private"},  # Por seguridad, nacen privadas
        }
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                url, headers=self.headers, params={"part": "snippet,status"}, json=body
            )
            return self._handle_response(response)

    def add_video_to_playlist(self, playlist_id: str, video_id: str):
        """Inserta un video en una playlist. Coste: 50 unidades."""
        url = f"{self.base_url}/playlistItems"
        body = {
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
            }
        }
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                url, headers=self.headers, params={"part": "snippet"}, json=body
            )
            return self._handle_response(response)
