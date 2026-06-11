# Worker Lambda — Contexto

## Qué hace
Procesa suscripciones de YouTube por lotes usando un Relay Pattern.
Cada invocación procesa una página de 50 suscripciones y se re-encola si hay más.

## Flujo de ejecución
1. Recibe mensaje SQS con `jobId` + `userId`
2. Lee el job de DynamoDB (obtiene `encryptedRefreshToken` y `nextPageToken`)
3. Descifra refresh token con KMS
4. Obtiene secrets de Google (client_id/secret) desde SSM (con caché global)
5. Refresca access token con Google OAuth2
6. Llama a YouTube API para obtener un lote de suscripciones
7. Actualiza progreso en DynamoDB (status, doneCount, nextPageToken)
8. Si hay más páginas → re-encola mensaje en SQS (relay)
9. Si no hay más páginas → marca job como DONE

## Estados del Job
- PENDING → esperando procesamiento
- RUNNING → procesando lotes
- DONE → todas las páginas completadas
- PAUSED_QUOTA → cuota de YouTube agotada, espera al Resumer

## Relay Pattern
En vez de procesar todas las páginas en una sola invocación (riesgo de timeout),
cada Lambda procesa un lote y se re-encola. Esto da:
- Resiliencia ante timeouts
- Visibilidad por lote en logs/X-Ray
- Reintento granular (solo el lote fallido va a DLQ)

## Dependencias internas (shared/)
- `security.decrypt_token` — descifra refresh token con KMS + Base64
- `google_auth.refresh_access_token` — intercambia refresh token por access token
- `youtube_client.YouTubeClient` — wrapper de YouTube Data API v3
- `exceptions` — QuotaExceededError, InvalidTokenError

## Clientes AWS utilizados
- S3 — almacenamiento de datos (actualmente no usado en handler, pendiente)
- DynamoDB — estado del job
- KMS — descifrado de tokens
- SSM — secrets de Google OAuth
- SQS — relay de mensajes

## Variables de entorno requeridas
- DYNAMODB_TABLE — nombre de la tabla de jobs
- SQS_QUEUE_URL — URL de la cola para relay
- AWS_ENDPOINT_URL — solo en local (LocalStack)

## Manejo de errores
- QuotaExceededError → marca PAUSED_QUOTA, retorna éxito (SQS borra mensaje)
- Cualquier otro error → raise (SQS reintenta, máx 3 antes de DLQ)

## Optimizaciones
- Caché global de secrets SSM (warm starts evitan llamadas redundantes)
- Timeout estricto en llamadas HTTP (5s Google, 10s YouTube)

## Pendiente
- Usar S3 para almacenar resultados parciales por lote
- Implementar Resumer para jobs en PAUSED_QUOTA
- Manejar InvalidTokenError (notificar al usuario)
- Paginación de export (subscribe a canales)

## Restricciones — nunca hacer esto
-No ejecutar cambios sin antes evaluar las consecuencias.
