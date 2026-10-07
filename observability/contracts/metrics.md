# Contrato inicial de métricas

## Componente inicial

```text
extension-worker-develop
extension-worker-prod
```

## Métricas

| Métrica | Fuente | Uso |
|---|---|---|
| `Errors` | `AWS/Lambda` | Errores de ejecución |
| `Invocations` | `AWS/Lambda` | Volumen de invocaciones |
| `Duration` | `AWS/Lambda` | Duración de ejecución |
| `Throttles` | `AWS/Lambda` | Invocaciones rechazadas por límite |

## Respuesta prevista

```json
{
  "environment": "develop",
  "component": "worker",
  "status": "healthy",
  "error_rate": 0,
  "invocations": 0,
  "errors": 0,
  "throttles": 0,
  "duration_p95_ms": 0
}
```

Los umbrales se aplicarán en el backend, no en la interfaz.
