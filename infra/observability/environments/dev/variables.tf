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

variable "log_retention_days" {
  description = "Retención de logs de la Lambda de observabilidad."
  type        = number
  default     = 14
}
