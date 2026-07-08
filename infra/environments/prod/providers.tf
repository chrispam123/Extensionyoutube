terraform {
  # 1. VERSIÓN DE TERRAFORM
  # Requerimos al menos la 1.10 para el S3-Native Locking que discutimos
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # 2. VERSIÓN DEL PROVIDER (EL DICCIONARIO)
      # Forzamos la versión 5.61.0 o superior para que Terraform
      # entienda la palabra 'recursive_loop' en las Lambdas.
      version = ">= 5.61.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  # 3. GESTIÓN DE IDENTIDAD HÍBRIDA
  # Si use_localstack es true, inyectamos credenciales de prueba.
  # Si es false, Terraform busca las credenciales reales en el entorno (OIDC/CLI).
  access_key = var.use_localstack ? "test" : null
  secret_key = var.use_localstack ? "test" : null

  # 4. COMPATIBILIDAD S3 (PATH STYLE)
  # Necesario para que LocalStack no falle con subdominios DNS inexistentes.
  s3_use_path_style = var.use_localstack

  # 5. SALTOS DE VALIDACIÓN PARA SIMULADORES
  # Evita que Terraform intente validar las llaves contra los servidores
  # reales de AWS cuando estamos trabajando en local.
  skip_credentials_validation = var.use_localstack
  skip_metadata_api_check     = var.use_localstack
  skip_requesting_account_id  = var.use_localstack

  # 6. DESVÍO DINÁMICO DE TRÁFICO (ENDPOINTS)
  # Si use_localstack es true, el GPS de Terraform apunta a tu PC (4566).
  dynamic "endpoints" {
    for_each = var.use_localstack ? [1] : []
    content {
      s3       = "http://localhost:4566"
      sqs      = "http://localhost:4566"
      dynamodb = "http://localhost:4566"
      lambda   = "http://localhost:4566"
      iam      = "http://localhost:4566"
      sts      = "http://localhost:4566"
      kms      = "http://localhost:4566"
      ssm      = "http://localhost:4566"
    }
  }
}
