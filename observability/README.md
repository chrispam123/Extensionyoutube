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

La Lambda se prueba inicialmente mediante invocación manual. Las fases posteriores podrán añadir SQS, DLQ, API Gateway, DynamoDB, panel web y alertas.

## Principios

- No duplicar la infraestructura existente de Nocturne.
- No exponer credenciales AWS al navegador.
- Mantener separado el código de observabilidad del backend público.
- Añadir infraestructura solo cuando una fase la necesite.
- Validar cada fase antes de avanzar.
