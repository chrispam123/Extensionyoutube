variable "aws_region" {
  description = "Región de AWS"
  type        = string
}

variable "use_localstack" {
  description = "Booleano para activar el desvío hacia LocalStack"
  type        = bool
}

variable "environment" {
  description = "Nombre del entorno (local, develop, prod)"
  type        = string
}
