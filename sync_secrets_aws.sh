#!/bin/bash
# -*- coding: utf-8 -*-
# Usage: ./sync_secrets_aws.sh [develop|prod]

ENV=$1

if [[ ! "$ENV" =~ ^(develop|prod)$ ]]; then
    echo "❌ ERROR: Debes especificar el entorno: develop o prod"
    echo "Ejemplo: ./sync_secrets_aws.sh develop"
    exit 1
fi

# 1. Cargar variables del .env
export $(grep -v '^#' .env | xargs)
unset AWS_ENDPOINT_URL AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN

echo "🌐 Conectando con AWS Cloud - Entorno: $ENV"

# 2. Verificación de Identidad
ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
echo "🎯 Cuenta AWS: $ACCOUNT_ID"

# 3. Inyectar Secretos con Ruta Dinámica
# Usamos el alias de la llave correspondiente al entorno
KMS_KEY="alias/extension/token-key-$ENV"

echo "🔑 Subiendo secretos a /extension/$ENV/..."

aws ssm put-parameter --name "/extension/$ENV/google/client_id" --value "$GOOGLE_CLIENT_ID" --type "String" --overwrite
aws ssm put-parameter --name "/extension/$ENV/google/client_secret" --value "$GOOGLE_CLIENT_SECRET" --type "SecureString" --key-id "$KMS_KEY" --overwrite
aws ssm put-parameter --name "/extension/$ENV/auth/jwt_secret" --value "$JWT_SECRET" --type "SecureString" --key-id "$KMS_KEY" --overwrite

echo "✅ Sincronización completada para $ENV."
