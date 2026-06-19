#!/bin/bash
# -*- coding: utf-8 -*-
# Project: Nocturne Backend
# Purpose: Sync real Google secrets to AWS Cloud (Develop Environment)

# 1. Cargar variables del .env
# Usamos export para que las variables estén disponibles para los comandos aws
export $(grep -v '^#' .env | xargs)
# --- EL ESCUDO: LIMPIEZA DE ENTORNO ---
# Borramos la variable del endpoint para que el CLI use los oficiales de AWS
unset AWS_ENDPOINT_URL
unset AWS_ACCESS_KEY_ID
unset AWS_SECRET_ACCESS_KEY
unset AWS_SESSION_TOKEN

echo "🌐 Conectando con AWS Cloud (Real)..."

# 2. Verificación de Identidad (Seguridad ante todo)
# Antes de subir nada, confirmamos en qué cuenta estamos para no equivocarnos
ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
if [ $? -ne 0 ]; then
    echo "❌ ERROR: No se pudo conectar con AWS Real. Revisa tus credenciales."
    exit 1
fi
echo "🎯 Operando en la cuenta AWS: $ACCOUNT_ID"

# 3. Inyectar Client ID
# Lo subimos como SecureString usando el alias de la llave que creó Terraform
echo "🔑 Subiendo Client ID..."
aws ssm put-parameter \
    --name "/extension/google/client_id" \
    --value "$GOOGLE_CLIENT_ID" \
    --type "SecureString" \
    --key-id "alias/extension/token-key-develop" \
    --overwrite

# 4. Inyectar Client Secret
echo "🔑 Subiendo Client Secret..."
aws ssm put-parameter \
    --name "/extension/google/client_secret" \
    --value "$GOOGLE_CLIENT_SECRET" \
    --type "SecureString" \
    --key-id "alias/extension/token-key-develop" \
    --overwrite

# 5. Inyectar JWT Secret para la firma de pasaportes Nocturne
echo "🔑 Subiendo JWT Secret..."
aws ssm put-parameter \
    --name "/extension/auth/jwt_secret" \
    --value "$JWT_SECRET" \
    --type "SecureString" \
    --key-id "alias/extension/token-key-develop" \
    --overwrite

echo "✅ Todos los secretos (Google + JWT) sincronizados en AWS Cloud."
