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

output "cognito_user_pool_id" {
  description = "ID del User Pool de Cognito para observabilidad."
  value       = aws_cognito_user_pool.observability.id
}

output "cognito_user_pool_client_id" {
  description = "ID del App Client público de Cognito para observabilidad."
  value       = aws_cognito_user_pool_client.observability.id
}

output "cognito_domain" {
  description = "Dominio hospedado de Cognito para el panel de observabilidad."
  value       = aws_cognito_user_pool_domain.observability.domain
}

output "cognito_hosted_ui_base_url" {
  description = "URL base del Hosted UI de Cognito."
  value       = "https://${aws_cognito_user_pool_domain.observability.domain}.auth.${var.aws_region}.amazoncognito.com"
}

output "observability_frontend_bucket_name" {
  description = "Bucket privado donde se alojará el frontend de observabilidad."
  value       = aws_s3_bucket.observability_frontend.id
}

output "observability_frontend_cloudfront_distribution_id" {
  description = "ID de la distribución CloudFront del frontend de observabilidad."
  value       = aws_cloudfront_distribution.observability_frontend.id
}

output "observability_frontend_url" {
  description = "URL HTTPS del frontend de observabilidad."
  value       = "https://${aws_cloudfront_distribution.observability_frontend.domain_name}"
}
