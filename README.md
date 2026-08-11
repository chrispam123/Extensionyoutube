# Nocturne — YouTube Backup & Restore

Extensión de Chrome para exportar e importar suscripciones y playlists de YouTube con detalles goticos y artesanales. Backend serverless en AWS con máquina de estados, cuota inteligente y side panel persistente.
Las decisiones de Arquitectura, patrones de diseño y seguridad 100% humanas.

---

## Características

- **Exportación completa**: canales + playlists con videos a JSON estructurado
- **Importación batch**: procesa cientos de canales en lotes de 10 con pausa por cuota
- **Side panel persistente**: no se cierra al cambiar de pestaña
- **WebGL Abyss**: shader de niebla azul con ruido procedural como fondo
- **Recuperación de sesión**: si cierras sesión, al volver recuperas el estado exacto del trabajo
- **Quota intelligence**: pausa automática cuando se agota la cuota de YouTube, reanuda al resetear

---

## Stack

| Capa | Tecnología |
|---|---|
| Frontend | React 18 + TypeScript + Vite |
| Backend | Python 3.12 + AWS Lambda + API Gateway |
| Base de datos | DynamoDB (Single Table Design + GSI) |
| Storage | S3 + presigned URLs |
| Colas | SQS (Worker + Ingestion + DLQ) |
| CI/CD | GitHub Actions + OIDC + Terraform |
| Testing | pytest + moto + black |

---

## Arquitectura

```
 [Chrome Side Panel]
       │
  React + TypeScript
       │
  API Gateway (HTTP v2)
       │
  ┌────┼────┬──────┬──────┐
  │    │    │      │      │
 Auth Upload Status Worker  Resumer
  │    │    │      │      │
  └────┴────┴──────┴──────┘
       │
  DynamoDB │ S3 │ SQS │ KMS │ SSM
```

---

## Flujo de estados del Worker

```
PENDING → RUNNING → DONE
              ↓
         PAUSED_QUOTA
              ↓
          Resumer → PENDING
```

---

## Estructura del proyecto

```
nocturne-backend/
├── frontend/
│   ├── src/
│   │   ├── App.tsx                 # UI principal (estados: login/success/progress/menu)
│   │   ├── background.ts            # Service Worker (OAuth, jobs, polling)
│   │   └── components/
│   │       ├── Layout.tsx           # Side panel wrapper
│   │       ├── RelicToggle.tsx      # Toggle canales/playlists
│   │       └── AbyssBackground.tsx  # WebGL shader
│   └── public/
│       └── manifest.json
├── src/
│   ├── worker/handler.py            # Lambda Worker (import/export engine)
│   ├── dispatcher/dispatcher.py     # S3 event → PENDING
│   ├── upload/upload.py             # API POST /jobs
│   ├── status/status.py             # API GET /status/{jobId}
│   ├── auth/auth_handler.py         # API POST /auth/login
│   ├── resumer/resumer.py           # Cron → PAUSED_QUOTA → PENDING
│   └── shared/                      # Capa común (YouTubeClient, auth, DB)
├── infra/environments/
│   ├── local/                       # LocalStack
│   ├── dev/                         # Desarrollo en AWS
│   └── prod/                        # Producción
├── tests/                           # pytest + moto
├── sync_secrets_aws.sh              # Poblar SSM con secretos
├── SPEC.md                          # Especificación completa
└── .github/workflows/               # CI/CD pipelines
```

---

## Quick Start (Desarrollo Local)

```bash
# 1. Entorno Python
poetry install
poetry run pytest

# 2. Frontend
cd frontend
npm install
npm run dev

# 3. Infraestructura (requiere LocalStack o AWS)
cd infra/environments/dev
terraform init
terraform apply

# 4. Secrets
./sync_secrets_aws.sh develop
```

---

## Despliegue

| Entorno | Rama | Pipeline |
|---|---|---|
| Dev | `develop` | CI: `black` + `pytest` → CD: `terraform apply` + `npm run build` |
| Prod | `main` | CI: `black` + `pytest` → CD: `terraform apply` + `npm run build` (strip `key`) |

---
Desarrollado por christian Gohring


## Licencia

MIT
