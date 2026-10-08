variable "aws_region" {
  description = "Región de AWS del stack de observabilidad."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Entorno observado por esta instalación."
  type        = string
  default     = "develop"
}

variable "observed_components" {
  description = "Componentes Lambda de Nocturne que observará el MVP."
  type        = list(string)
  default     = ["auth", "upload", "dispatcher", "worker", "status", "resumer"]
}

variable "observed_queues" {
  description = "Colas SQS y DLQ de Nocturne que observará el MVP."
  type        = list(string)
  default     = ["work", "dlq", "ingestion", "ingestion-dlq"]
}

variable "log_retention_days" {
  description = "Retención de logs de la Lambda de observabilidad."
  type        = number
  default     = 14
}

variable "api_gateway_stage" {
  description = "Stage del HTTP API de Nocturne que se observará."
  type        = string
  default     = "develop"
}

variable "api_gateway_id" {
  description = "ID del HTTP API de Nocturne que se observará."
  type        = string
  default     = "pugu65me5k"
}

variable "eventbridge_rule_name" {
  description = "Regla EventBridge del resumer que se observará."
  type        = string
  default     = "extension-resumer-cron-develop"
}

variable "eventbridge_target_function" {
  description = "Lambda target de la regla EventBridge."
  type        = string
  default     = "extension-resumer-develop"
}

variable "cognito_domain_prefix" {
  description = "Prefijo global del dominio Cognito para el panel de observabilidad."
  type        = string
  default     = "nocturne-observability-dev-380894"
}

variable "cognito_callback_urls" {
  description = "URI de callback autorizadas para el App Client de observabilidad."
  type        = list(string)
  default     = ["http://localhost:5173/auth/callback"]
}

variable "cognito_logout_urls" {
  description = "URI de salida autorizadas para el App Client de observabilidad."
  type        = list(string)
  default     = ["http://localhost:5173/"]
}
