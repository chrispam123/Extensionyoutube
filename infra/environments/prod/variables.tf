variable "aws_region" {
  description = "Región de AWS"
  type        = string
}

variable "use_localstack" {
  description = "Booleano para activar el desvío hacia LocalStack"
  type        = bool
}

#con esto definiremos el nombre de cada recurso en aws para asi saber y poder diferenciar bien
variable "environment" {
  description = "Nombre del entorno (local, develop, prod)"
  type        = string
}
variable "extension_id" {
  description = "ID único de la extensión de Chrome (obtenido de la tienda)"
  type        = string
}
