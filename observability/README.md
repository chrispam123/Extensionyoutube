# Nocturne Observability

MVP incremental de observabilidad para Nocturne.

## Alcance de la fase 1

La primera fase observa las seis Lambdas de un entorno leyendo las métricas existentes de CloudWatch:

- `auth`
- `upload`
- `dispatcher`
- `worker`
- `status`
- `resumer`

También observa las colas SQS del flujo:

- `work` y su `dlq`
- `ingestion` y su `ingestion-dlq`

También consulta los jobs mediante el índice DynamoDB `StatusIndex` y calcula
recuentos por estado y antigüedad de jobs pendientes o ejecutándose.

También consulta el HTTP API Gateway del entorno para observar peticiones,
errores `4xx`/`5xx` y latencia p95.

Métricas iniciales:

- `Errors`
- `Invocations`
- `Duration`
- `Throttles`

La fase 1 no crea todavía un panel web, un API Gateway, una base de datos de snapshots, alarmas ni notificaciones.

## Arquitectura incremental

```text
Lambda Observability
        |
        | boto3, permisos IAM de lectura
        v
CloudWatch existente de Nocturne
```

La Lambda se prueba inicialmente mediante invocación manual. Las fases posteriores podrán añadir API Gateway, DynamoDB, panel web y alertas.

## Principios

- No duplicar la infraestructura existente de Nocturne.
- No exponer credenciales AWS al navegador.
- Mantener separado el código de observabilidad del backend público.
- Añadir infraestructura solo cuando una fase la necesite.
- Validar cada fase antes de avanzar.
