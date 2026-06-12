# Infraestructura Dev — Contexto

## Qué es
Entorno de desarrollo en AWS real. Se despliega automáticamente via GitHub Actions (CD)
al hacer push/merge a la rama `develop`.

## Cómo funciona
1. GitHub Actions asume un rol IAM via OIDC (sin secretos estáticos)
2. Construye el artefacto Lambda (deps + handler + shared)
3. Terraform aplica la infraestructura con `use_localstack = false`
4. El estado de Terraform se guarda en S3 real con lock nativo

## Recursos provisionados

| Recurso | Nombre | Propósito |
|---------|--------|-----------|
| DynamoDB | extension-dynamo-jobs-develop | Estado de jobs (PK: jobId) |
| S3 | extension-s3-uploads-develop | JSON de suscripciones |
| SQS Main | extension-sqs-work-develop | Cola de trabajos |
| SQS DLQ | extension-sqs-dlq-develop | Mensajes fallidos (3 reintentos) |
| Lambda | extension-worker-develop | Procesador de suscripciones |
| KMS Key | alias/extension/token-key-develop | Cifrado de refresh tokens |
| SSM | /extension/google/client_id | Client ID de Google OAuth |
| SSM | /extension/google/client_secret | Client Secret de Google OAuth |
| IAM Role | extension-worker-role-develop | Identidad de la Lambda |

## Permisos IAM de la Lambda (mínimo privilegio)
- logs: CreateLogGroup, CreateLogStream, PutLogEvents
- s3: GetObject (solo en el bucket de uploads)
- dynamodb: UpdateItem, GetItem (solo en tabla de jobs)
- kms: Decrypt (solo en la key de tokens)
- sqs: ReceiveMessage, DeleteMessage, GetQueueAttributes (consumir cola)
- sqs: SendMessage (auto-invocación/replay)
- ssm: GetParameter (solo en los 2 parámetros de Google)

## Archivos Terraform
- `main.tf` — todos los recursos y outputs
- `providers.tf` — provider AWS (endpoints nativos, sin LocalStack)
- `variables.tf` — aws_region, use_localstack, environment
- `terraform.tfvars` — valores: us-east-1, use_localstack=false, environment=develop
- `backend.tf` — state en S3 (key: dev/terraform.tfstate)

## Backend del estado
- Bucket S3: `extension-terraform-state-youtube`
- Key: `dev/terraform.tfstate`
- Lock: nativo S3 (use_lockfile = true)
- NUNCA modificar el state manualmente

## Variables inyectadas a la Lambda
- S3_BUCKET = extension-s3-uploads-develop
- DYNAMODB_TABLE = extension-dynamo-jobs-develop
- KMS_KEY_ALIAS = alias/extension/token-key-develop
- SQS_QUEUE_URL = URL de la cola (generada por Terraform)
- AWS_ENDPOINT_URL NO se inyecta (usa endpoints nativos de AWS)

## SSM Parameters (Secretos)
- Creados por Terraform con valor placeholder "REPLACE_ME"
- Se llenan via `sync_secrets_aws.sh` como SecureString cifrado con KMS
- lifecycle.ignore_changes evita que Terraform los sobrescriba en applies futuros

## CD Pipeline (GitHub Actions)
- Trigger: push a `develop`
- Autenticación: OIDC → assume role (secreto: AWS_ROLE_ARN)
- Build: poetry export → pip install → copiar handler + shared
- Deploy: terraform init → terraform apply -auto-approve

## Flujo de trabajo
1. Push/merge a `develop` dispara el CD
2. GitHub Actions construye artefacto y aplica Terraform
3. Primera vez: ejecutar `sync_secrets_aws.sh` para subir secretos reales a SSM

## Pendiente
- Quitar paso de diagnóstico del CD cuando el pipeline sea estable
- Refactor a módulo Terraform compartido con local
