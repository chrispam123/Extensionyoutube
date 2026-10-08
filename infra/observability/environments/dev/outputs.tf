output "observability_function_name" {
  description = "Nombre de la Lambda del MVP de observabilidad."
  value       = aws_lambda_function.observability.function_name
}

output "observability_log_group_name" {
  description = "Grupo de logs de la Lambda de observabilidad."
  value       = aws_cloudwatch_log_group.observability.name
}

output "observability_api_url" {
  description = "URL base del API HTTP independiente de observabilidad."
  value       = "${aws_apigatewayv2_api.observability.api_endpoint}/${aws_apigatewayv2_stage.observability.name}/observability"
}

output "observability_api_id" {
  description = "ID del API HTTP independiente de observabilidad."
  value       = aws_apigatewayv2_api.observability.id
}
