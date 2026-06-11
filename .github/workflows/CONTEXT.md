# CI Pipeline — Contexto

## Qué hace
Valida calidad de código en cada push/PR: formato (Black) + tests unitarios (pytest + moto).

## Triggers
- Push a `develop` y `feature/*`
- Pull requests hacia `main` o `develop`

## Job: validate
Runner: ubuntu-latest

### Variables de entorno
- AWS_ACCESS_KEY_ID/SECRET/TOKEN = "testing" → credenciales fake para moto
- AWS_DEFAULT_REGION = us-east-1
- PYTHONPATH = src → permite imports como `from shared.x import y`

### Steps
1. Checkout código
2. Setup Python 3.12
3. Instalar Poetry (virtualenvs in-project)
4. Cache de .venv (key basada en poetry.lock)
5. Install deps (solo si no hay cache hit)
6. `black --check .` → falla si hay código sin formatear
7. `pytest` → ejecuta tests unitarios con moto (sin AWS real)

## Decisiones de diseño
- Credenciales fake: moto necesita que existan variables AWS aunque no se usen
- PYTHONPATH=src: evita instalar el paquete como editable para resolver imports
- Cache por poetry.lock: se invalida solo cuando cambian dependencias
- No hay CD: deploy es manual por ahora

## Pendiente
- Agregar coverage report (pytest-cov)
- Workflow CD para deploy a dev/prod
- Posible matrix para múltiples versiones de Python
