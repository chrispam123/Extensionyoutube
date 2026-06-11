# Infraestructura Local — Contexto

## Qué es
Entorno de desarrollo local que replica la infraestructura AWS usando LocalStack Pro + Terraform.
Permite iterar sin costos ni riesgos sobre AWS real.

## Cómo funciona
1. LocalStack levanta servicios AWS en `localhost:4566` (docker-compose)
2. Terraform apunta sus endpoints a LocalStack via `use_localstack = true`
3. El estado de Terraform se guarda en S3 real (AWS) — nunca en local

## Recursos provisionados

| Recurso | Nombre | Propósito |
|---------|--------|-----------|
| DynamoDB | extension-dynamo-jobs-local | Estado de jobs (PK: jobId) |
| S3 | extension-s3-uploads-local | JSON de suscripciones |
| SQS Main | extension-sqs-work-local | Cola de trabajos |
| SQS DLQ | extension-sqs-dlq-local | Mensajes fallidos (3 reintentos) |
| Lambda | extension-worker-local | Procesador de suscripciones |
| KMS Key | alias/extension/token-key | Cifrado de refresh tokens |
| SSM | /extension/google/client_id | Client ID de Google OAuth |
| SSM | /extension/google/client_secret | Client Secret de Google OAuth |
| IAM Role | extension-worker-role-local | Identidad de la Lambda |

## Permisos IAM de la Lambda (mínimo privilegio)
- logs: CreateLogGroup, CreateLogStream, PutLogEvents
- s3: GetObject (solo en el bucket de uploads)
- dynamodb: UpdateItem, GetItem (solo en tabla de jobs)
- kms: Decrypt (solo en la key de tokens)
- sqs: SendMessage (solo en la cola principal — relay)
- ssm: GetParameter (solo en los 2 parámetros de Google)

## Archivos Terraform
- `main.tf` — todos los recursos y outputs
- `providers.tf` — provider AWS con desvío condicional a LocalStack
- `variables.tf` — aws_region, use_localstack
- `terraform.tfvars` — valores: us-east-1, use_localstack=true
- `backend.tf` — state en S3 real (bucket: extension-terraform-state-youtube)

## Backend del estado
- Bucket S3 real: `extension-terraform-state-youtube`
- Key: `local/terraform.tfstate`
- Lock: nativo S3 (use_lockfile = true, sin DynamoDB)
- NUNCA modificar el state manualmente

## LocalStack (docker-compose)
- Imagen: localstack/localstack-pro:latest
- Puerto: 4566
- Servicios: s3, sqs, dynamodb, lambda, kms, ssm, iam, logs, xray
- Persistencia: desactivada (PERSISTENCE=0)
- Variables: cargadas desde /.env

## Variables inyectadas a la Lambda
- AWS_ENDPOINT_URL = http://localhost.localstack.cloud:4566
- S3_BUCKET = extension-s3-uploads-local
- DYNAMODB_TABLE = extension-dynamo-jobs-local
- KMS_KEY_ALIAS = alias/extension/token-key
- SQS_QUEUE_URL = URL de la cola (generada por Terraform)

## SSM Parameters
- Creados con valor "REPLACE_ME" por Terraform
- Se llenan via CLI (awslocal ssm put-parameter)
- lifecycle.ignore_changes evita que Terraform los sobrescriba

## Deploy manual (deploy.sh)
- DEPRECADO parcialmente — usa naming viejo (nocturne-*)
- Flujo: limpiar dist → exportar deps → copiar handler → zip → crear Lambda → conectar SQS
- Para deploy actual usar: `terraform apply`

## Flujo de trabajo
1. `docker compose up -d` (levantar LocalStack)
2. `terraform init` (solo primera vez)
3. `terraform apply` (crear/actualizar recursos)
4. Llenar SSM secrets via awslocal si es primera vez
5. Iterar sobre código y re-aplicar

## Pendiente
- Eliminar init-aws.sh (deprecado)
- Actualizar deploy.sh al naming correcto o eliminarlo
- Agregar entornos dev y prod con variables reales
