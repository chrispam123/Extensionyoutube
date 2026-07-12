provider "aws" {
  region = var.aws_region

  # 1. AUTO-INYECCIÓN DE CREDENCIALES PARA LOCALSTACK
  # Si use_localstack es true, forzamos "test".
  # Si es false, Terraform usará las de tu terminal (las reales).
  access_key = var.use_localstack ? "test" : null
  secret_key = var.use_localstack ? "test" : null
  token      = var.use_localstack ? "test" : null
  # ESTAS DOS LÍNEAS SON LA SOLUCIÓN:para que cree s3 bucket ntenta comunicarse con S3 usando un estilo de URL llamado Virtual Hosted-Style (ejemplo: extension-s3-uploads-local.s3.localhost.localstack.cloud
  s3_use_path_style           = var.use_localstack

  # 2. ELIMINAMOS EL FRENO DE MANO TEMPORALMENTE
  # Para que LocalStack no se confunda con STS, vamos a saltar la validación
  skip_credentials_validation = var.use_localstack
  skip_metadata_api_check     = var.use_localstack
  skip_requesting_account_id  = var.use_localstack # <--- ESTO EVITA EL ERROR DE STS

  dynamic "endpoints" {
    for_each = var.use_localstack ? [1] : []
    content {
      s3       = "http://localhost:4566"
      sqs      = "http://localhost:4566"
      dynamodb = "http://localhost:4566"
      lambda   = "http://localhost:4566"
      iam      = "http://localhost:4566"
      sts      = "http://localhost:4566"
      kms      = "http://localhost:4566" # <--- Asegúrate de que esta línea esté
      ssm = "http://localhost:4566"

    }
  }
}
