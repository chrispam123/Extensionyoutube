# Pruebas de observabilidad

Las pruebas iniciales cubrirán:

- Cálculo de `error_rate`.
- Clasificación `healthy`, `warning` y `critical`.
- Respuesta cuando CloudWatch no devuelve invocaciones.
- Separación correcta entre `develop` y `prod`.

No se realizarán llamadas reales a AWS en las pruebas unitarias.
