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

variable "google_mobile_client_id" {
  description = "ID de cliente Google OAuth2 para la app Android"
  type        = string
  default     = ""
}

variable "google_mobile_redirect_uri" {
  description = "URI de redirección autorizada de Google OAuth2 para la app Android"
  type        = string
  default     = ""
}

