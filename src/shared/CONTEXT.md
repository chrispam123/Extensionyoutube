# Shared Module — Contexto

## Qué es
Capa de utilidades compartidas entre Lambdas. Contiene lógica de seguridad,
autenticación con Google y cliente de YouTube API.

## Módulos

### security.py
- `decrypt_token(kms_client, ciphertext_b64)` → descifra refresh token
- Flujo: Base64 decode → KMS Decrypt → string UTF-8
- No necesita KeyId (viene incrustado en el ciphertext)

### google_auth.py
- `refresh_access_token(client_id, client_secret, refresh_token)` → access token fresco
- Llama a `https://oauth2.googleapis.com/token` con grant_type=refresh_token
- Timeout: 5 segundos (evitar colgar la Lambda)
- Usa httpx (no requests)

### youtube_client.py
- Clase `YouTubeClient(access_token)`
- Método `get_subscriptions(max_results=50, page_token=None)` → respuesta paginada
- Mapeo de errores:
  - 403 quotaExceeded → QuotaExceededError
  - 401 → InvalidTokenError
- Timeout: 10 segundos
- Usa httpx

### exceptions.py
- `NocturneError` — base de todos los errores del proyecto
- `QuotaExceededError` — cuota YouTube agotada
- `InvalidTokenError` — token revocado o expirado

## Dependencias externas
- httpx — cliente HTTP async-compatible (usado sync aquí)
- boto3 — solo para type hints en security.py
- aws-lambda-powertools — Logger para observabilidad

## Convenciones
- Cada función loggea errores antes de re-raise
- Timeouts explícitos en toda llamada HTTP
- Sin estado global (excepto logger)
- Errores tipados para que el worker decida qué hacer con cada caso

## Pendiente
- Manejar InvalidTokenError en el worker (notificar usuario)
- Agregar método subscribe/unsubscribe a YouTubeClient
- Tests unitarios dedicados para cada módulo shared
