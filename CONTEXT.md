# Nocturne Backend — Contexto del Proyecto

## Qué es
Backend serverless para una extensión de YouTube que
importa/exporta suscripciones de cualquier cuenta de usuario.

## Arquitectura
[Extensión YouTube] → API → SQS → Lambda Worker → S3 + DynamoDB

- SQS Main Queue → dispara Lambda (batch size 1)
- SQS DLQ → mensajes fallidos (maxReceiveCount: 3)
- Lambda Worker → lee JSON de S3, actualiza estado en DynamoDB
- S3 → almacena datos exportados/importados (JSON canales/playlists)
- DynamoDB → tabla de jobs (PK: jobId)
- Patrón Claim Check → SQS lleva solo jobId + userId, datos pesados en S3

## Stack
- Lenguaje: Python 3.12
- Gestión deps: Poetry
- IaC: Terraform (state en S3 real con lock nativo)
- Local: LocalStack Pro (docker-compose)
- Observabilidad: aws-lambda-powertools (Logger + Tracer/X-Ray)
- Testing: pytest + moto + pytest-mock
- Lint/Format: Black + pre-commit hooks
- CI/CD: GitHub Actions

## Entornos
- local: LocalStack + Terraform — funcional
- dev: AWS real — funcional (CI + CD + OIDC + Terraform state en S3)
- prod: AWS real — pendiente

## Estructura
nocturne-backend/
├── src/worker/handler.py        # Lambda principal
├── tests/
│   ├── test_handler.py          # Tests unitarios (moto)
│   └── fire_bullet.py           # Test integración manual (LocalStack)
├── infra/enviroments/
│   ├── local/
│   ├── dev/
│   └── prod/
├── docker/localstack/
│   ├── docker-compose.yml
│   └── init-aws.sh             # DEPRECADO — pendiente eliminar
├── dist/                        # Artefactos Lambda ZIP
├── deploy.sh                    # Deploy manual LocalStack
├── sync_secrets_aws.sh          # Sube secretos Google a SSM (dev)
└── .github/workflows/
    ├── ci-validation.yml
    └── cd-deploy.yml            # CD: build + Terraform apply en dev

## Naming de recursos
- Convención: extension-{recurso}-{entorno}
- Ejemplos: extension-dynamo-jobs-local, extension-sqs-main-dev
- Fuente de verdad: Terraform
- NUNCA usar prefijo nocturne-* — deprecado, solo en init-aws.sh

## Variables de entorno
- AWS_ENDPOINT_URL — endpoint LocalStack (solo local)
- DYNAMODB_TABLE — nombre tabla DynamoDB
- S3_BUCKET — nombre bucket S3
- SQS_QUEUE_NAME — nombre cola SQS
- AWS_REGION — us-east-1
- Nunca en código — siempre desde variables de entorno o SSM

## Worker Lambda — flujo de estados
PENDING → RUNNING → DONE
1. Mensaje llega de SQS con jobId + userId
2. Lambda actualiza DynamoDB a RUNNING
3. Lee JSON de S3 usando jobId
4. Procesa suscripciones
5. Actualiza DynamoDB a DONE

## Restricciones críticas
- IAM: mínimo privilegio — nunca Action: "*" ni Resource: "*" juntos
- Naming: siempre extension-{recurso}-{entorno} — sin excepciones
- Secrets: ninguna credencial en código ni hardcodeada en Terraform
- Estado Terraform: nunca modificar el backend S3 manualmente
- init-aws.sh: no usar como referencia — está deprecado
- Tests: moto para unitarios, nunca llamadas reales a AWS en pytest

## Fase actual
Bala trazadora end-to-end funcional en local:
1. JSON de suscripciones subido a S3
2. Job PENDING creado en DynamoDB
3. Mensaje enviado a SQS
4. Lambda procesa: RUNNING → lee S3 → DONE

## Pendiente
- Infraestructura Terraform prod
- API Gateway
- Lógica real YouTube API
- Edge cases en tests
- Coverage en CI
- Refactor: extraer módulo Terraform compartido (infra/modules)
