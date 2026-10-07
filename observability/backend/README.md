# Backend de observabilidad

Aquí vivirá el código Python de la Lambda de observabilidad.

Responsabilidad inicial:

1. Consultar métricas de CloudWatch con `boto3`.
2. Calcular la tasa de errores y el estado del componente.
3. Devolver un JSON normalizado.

En esta fase no se expone ningún endpoint HTTP. La Lambda se invocará manualmente para validar permisos, consultas y formato de respuesta.
