#!/bin/bash
# -*- coding: utf-8 -*-
# Project: Nocturne Backend
# Purpose: Local Deployment for Tracer Bullet

set -e # Detener el script si algún comando falla

echo "🚀 Iniciando despliegue de la Bala Trazadora en LocalStack..."

# 1. Limpieza de artefactos previos
rm -rf dist/
mkdir -p dist/lambda

# 2. Empaquetado (Packaging)
echo "📦 Preparando el paquete de la Lambda..."
poetry export -f requirements.txt --output dist/lambda/requirements.txt
pip install -r dist/lambda/requirements.txt -t dist/lambda/ --quiet
cp src/worker/handler.py dist/lambda/

# Crear el ZIP (silenciosamente)
cd dist/lambda && zip -r ../worker.zip . > /dev/null && cd ../..

# 3. Despliegue en LocalStack
echo "☁️  Subiendo Lambda a LocalStack..."

# Intentar borrar la función por si ya existe (para que sea un despliegue limpio)
awslocal lambda delete-function --function-name nocturne-worker-local 2>/dev/null || true

awslocal lambda create-function \
    --function-name nocturne-worker-local \
    --runtime python3.12 \
    --handler handler.lambda_handler \
    --zip-file fileb://dist/worker.zip \
    --role arn:aws:iam::000000000000:role/nocturne-role-local \
    --environment "Variables={AWS_ENDPOINT_URL=http://localhost:4566, DYNAMODB_TABLE=nocturne-dynamo-jobs-local, S3_BUCKET=nocturne-s3-uploads-local}"

# 4. Configuración del Trigger (SQS -> Lambda)
echo "🔗 Conectando SQS con la Lambda..."

# Obtener el ARN de la cola de forma automática (Sin copy-paste manual)
QUEUE_ARN=$(awslocal sqs get-queue-attributes \
    --queue-url http://localhost:4566/000000000000/nocturne-sqs-main-local \
    --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)

# Crear el mapeo de eventos
awslocal lambda create-event-source-mapping \
    --function-name nocturne-worker-local \
    --event-source-arn "$QUEUE_ARN" \
    --batch-size 1

echo "✅ Despliegue completado. La Bala Trazadora está lista para el impacto."
