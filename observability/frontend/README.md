# Nocturne Observability Frontend

Minimal React/Vite MVP for the read-only observability panel.

## Local setup

```powershell
npm install
Copy-Item .env.example .env.local
npm run dev
```

Set the real Cognito App Client ID in `.env.local`. The client secret is never used by this frontend.

The MVP uses Authorization Code + PKCE with Cognito Hosted UI and calls the observability API with the Cognito access token. The API Gateway route must use a Cognito JWT authorizer before the authenticated API request can succeed; until then, the login flow can be tested but the API request is expected to return `403` because the current route still uses IAM authorization.
