# Nocturne Backend — Contexto del Proyecto

## Qué es

Backend serverless para una extensión de YouTube que importa/exporta suscripciones de cualquier cuenta de usuario.

## Arquitectura

```
[Extensión YouTube] → API → SQS → Lambda Worker → S3 + DynamoDB
```

- **SQS Main Queue** → dispara Lambda (batch size 1)
- **SQS DLQ** → mensajes fallidos (maxReceiveCount: 3)
- **Lambda Worker** → lee JSON de S3, actualiza estado en DynamoDB
- **S3** → almacena datos exportados/importados (JSON con canales/playlists)
- **DynamoDB** → tabla de jobs (PK: `jobId`, estados: PENDING → RUNNING → DONE)
- **Patrón Claim Check** → SQS lleva solo `jobId` + `userId`, datos pesados en S3

## Stack Técnico

- **Lenguaje:** Python 3.12
- **Gestión deps:** Poetry
- **IaC:** Terraform (state en S3 real con lock nativo)
- **Local:** LocalStack Pro (docker-compose)
- **Observabilidad:** aws-lambda-powertools (Logger + Tracer/X-Ray)
- **Testing:** pytest + moto (mocks AWS) + pytest-mock
- **Lint/Format:** Black + pre-commit hooks
- **CI/CD:** GitHub Actions

## Entornos

| Entorno | Estado | Infra |
|---------|--------|-------|
| local | ✅ Funcional | LocalStack + Terraform |
| dev | 🔲 Pendiente | AWS real |
| prod | 🔲 Pendiente | AWS real |

## Estructura del Proyecto

```
nocturne-backend/
├── src/worker/handler.py        # Lambda principal
├── tests/
│   ├── test_handler.py          # Tests unitarios (moto)
│   └── fire_bullet.py           # Test integración manual (LocalStack)
├── infra/enviroments/
│   ├── local/                   # Terraform para LocalStack
│   ├── dev/                     # (pendiente)
│   └── prod/                    # (pendiente)
├── docker/localstack/
│   ├── docker-compose.yml
│   └── init-aws.sh             # Bootstrap recursos LocalStack
├── dist/                        # Artefactos de deploy (Lambda ZIP)
├── deploy.sh                    # Deploy manual a LocalStack
├── .github/workflows/
│   └── ci-validation.yml        # CI: lint + tests
└── .env                         # Variables locales (no versionado)
```

## CI/CD Actual

### CI (`ci-validation.yml`)
- **Triggers:** push a `develop` y `feature/*`, PRs a `main`/`develop`
- **Steps:** checkout → Python 3.12 → Poetry → cache venv → install deps → Black --check → pytest
- **Entorno:** credenciales fake de AWS para moto

### CD
- No implementado aún. Deploy local es manual (`deploy.sh` o `terraform apply`).

## Terraform

- **Backend:** S3 (`extension-terraform-state-youtube`, key: `local/terraform.tfstate`)
- **Lock:** Nativo S3 (use_lockfile = true, sin DynamoDB)
- **Provider local:** Endpoints redirigidos a `localhost:4566`, credenciales fake
- **Recursos:** DynamoDB table, S3 bucket, SQS queues (main + DLQ), IAM role, Lambda, Event Source Mapping

## Naming

- Convención: `extension-{recurso}-{entorno}` (ej: `extension-dynamo-jobs-local`)
- Fuente de verdad: Terraform
- `init-aws.sh` está deprecado (pendiente de eliminar), usaba prefijo `nocturne-*`

## Variables de Entorno (.env)

- `AWS_ENDPOINT_URL` — endpoint LocalStack
- `DYNAMODB_TABLE` — nombre tabla DynamoDB
- `S3_BUCKET` — nombre bucket S3
- `SQS_QUEUE_NAME` — nombre cola SQS
- `AWS_REGION` — us-east-1

## Fase Actual

**Bala Trazadora (Tracer Bullet)** — flujo end-to-end funcional en local:
1. Se sube JSON de suscripciones YouTube a S3
2. Se crea job PENDING en DynamoDB
3. Se envía mensaje a SQS
4. Lambda procesa: actualiza a RUNNING → lee S3 → actualiza a DONE

## Pendiente

- [ ] Workflow CD (deploy a dev/prod)
- [ ] Infraestructura Terraform para dev y prod
- [ ] API Gateway / endpoint para la extensión
- [ ] Lógica real de import/export YouTube API
- [ ] Más tests (edge cases, errores)
- [ ] Coverage en CI
