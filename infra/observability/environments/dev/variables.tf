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

variable "observed_worker_function" {
  description = "Nombre de la Lambda worker cuyas métricas consulta el MVP."
  type        = string
  default     = "extension-worker-develop"
}

variable "worker_timeout_ms" {
  description = "Timeout configurado para la worker, usado para calcular el umbral de duración."
  type        = number
  default     = 60000
}

variable "log_retention_days" {
  description = "Retención de logs de la Lambda de observabilidad."
  type        = number
  default     = 14
}
