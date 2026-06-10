#!/bin/bash
# -*- coding: utf-8 -*-
# Purpose: Sync real Google secrets from .env to LocalStack SSM

# Cargar variables del .env (ignorando comentarios)
export $(grep -v '^#' .env | xargs)

echo "🔐 Inyectando secretos de Google en LocalStack SSM..."

# Inyectar Client ID real que esta .env
poetry run awslocal ssm put-parameter \
    --name "/extension/google/client_id" \
    --value "$GOOGLE_CLIENT_ID" \
    --type "String" \
    --overwrite

# Inyectar Client Secret real que esta en .env
poetry run awslocal ssm put-parameter \
    --name "/extension/google/client_secret" \
    --value "$GOOGLE_CLIENT_SECRET" \
    --type "String" \
    --overwrite

echo "✅ Secretos sincronizados."
