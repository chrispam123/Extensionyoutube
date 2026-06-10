resource "aws_dynamodb_table" "jobs_table" {
  name         = "extension-dynamo-jobs-local"
  billing_mode = "PAY_PER_REQUEST" # Mentalidad Serverless: solo pagas por lo que usas
  hash_key     = "jobId"         # Nuestra Partition Key (PK)

  attribute {
    name = "jobId"
    type = "S" # String
  }

  tags = {
    Project     = "Nocturne"
    Environment = "Local"
  }
}


# 1. El Bunker S3 donde se suben los canales y playslits
resource "aws_s3_bucket" "uploads_bucket" {
  bucket = "extension-s3-uploads-local"

  # En local, permitimos que se borre aunque tenga archivos al hacer 'destroy'
  force_destroy = true

  tags = {
    Project = "Nocturne"
  }
}

# 2. La Cola de Mensajes Muertos (DLQ)
resource "aws_sqs_queue" "jobs_dlq" {
  name = "extension-sqs-dlq-local"
}

# 3. La Cola Principal (conectada a la DLQ)
resource "aws_sqs_queue" "jobs_queue" {
  name = "extension-sqs-work-local"

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.jobs_dlq.arn
    maxReceiveCount     = 3
  })
}
# =============================================================================
# 1. SEGURIDAD: ROL DE IAM PARA LA LAMBDA
# =============================================================================

# El "Contenedor" de la identidad
resource "aws_iam_role" "worker_role" {
  name = "extension-worker-role-local"

  # Trust Policy: Permite que el servicio Lambda "asuma" este rol
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

# Los "Poderes" del rol: Privilegio Mínimo
resource "aws_iam_role_policy" "worker_permissions" {
  name = "extension-worker-permissions-local"
  role = aws_iam_role.worker_role.id # <--- Referencia actualizada

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Permiso para escribir logs (Observabilidad)
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Effect   = "Allow"
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        # Permiso para el Bunker S3
        Action   = ["s3:GetObject"]
        Effect   = "Allow"
        Resource = "${aws_s3_bucket.uploads_bucket.arn}/*"
      },
      {
        # Permiso para el Cerebro DynamoDB
        Action   = ["dynamodb:UpdateItem", "dynamodb:GetItem"]
        Effect   = "Allow"
        Resource = aws_dynamodb_table.jobs_table.arn
      },
       # --- NUEVO PERMISO: DESCIFRADO ---
      {
        Action   = ["kms:Decrypt"]
        Effect   = "Allow"
        Resource = aws_kms_key.token_key.arn
      }
    ]
  })
}

# =============================================================================
# 2. EMPAQUETADO: CREACIÓN AUTOMÁTICA DEL ZIP
# =============================================================================

# Terraform genera el ZIP por nosotros.
# NOTA: Para que esto funcione, las dependencias deben estar en la carpeta dist/lambda
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../dist/lambda"
  output_path = "${path.module}/../../../dist/worker.zip"
}

# =============================================================================
# 3. COMPUTACIÓN: LA FUNCIÓN LAMBDA WORKER DE MOMENTO
# =============================================================================

resource "aws_lambda_function" "worker_lambda" {
  function_name    = "extension-worker-local"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256 # Detecta cambios en el código

  handler = "handler.lambda_handler"
  runtime = "python3.12"
  timeout = 30
  role    = aws_iam_role.worker_role.arn # <--- Referencia actualizada

  # INYECCIÓN DE DEPENDENCIAS:
  # Terraform pasa los nombres reales de los recursos a la Lambda
  environment {
    variables = {
      AWS_ENDPOINT_URL = "http://localhost.localstack.cloud:4566"
      S3_BUCKET        = aws_s3_bucket.uploads_bucket.id
      DYNAMODB_TABLE   = aws_dynamodb_table.jobs_table.name
      KMS_KEY_ALIAS    = aws_kms_alias.token_key_alias.name # <--- INYECCIÓN
    }
  }
}

# =============================================================================
# 4. EVENTOS: CONEXIÓN SQS -> LAMBDA (TRIGGER)
# =============================================================================

resource "aws_lambda_event_source_mapping" "sqs_trigger" {
  event_source_arn = aws_sqs_queue.jobs_queue.arn
  function_name    = aws_lambda_function.worker_lambda.arn
  batch_size       = 1
  enabled          = true
}

# 1. LA LLAVE MAESTRA
resource "aws_kms_key" "token_key" {
  description             = "Llave para Refresh Tokens"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  # Key Policy básica para permitir que IAM gestione los permisos
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Enable IAM User Permissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::000000000000:root" # En AWS real sería tu cuenta
        }
        Action   = "kms:*"
        Resource = "*"
      }
    ]
  })
}

# 2. EL ALIAS (La dirección postal amigable)
resource "aws_kms_alias" "token_key_alias" {
  name          = "alias/extension/token-key"
  target_key_id = aws_kms_key.token_key.key_id
}




# =============================================================================
# OUTPUTS: La "Factura" de la Infraestructura con esto se actualiza el .env
# =============================================================================

output "dynamodb_table_name" {
  value = aws_dynamodb_table.jobs_table.name
}

output "s3_bucket_name" {
  value = aws_s3_bucket.uploads_bucket.id
}

output "sqs_queue_name" {
  value = aws_sqs_queue.jobs_queue.name
}
