# El robot se mira al espejo para saber su ID de cuenta real
data "aws_caller_identity" "current" {}

resource "aws_dynamodb_table" "jobs_table" {
  name         = "extension-dynamo-jobs-${var.environment}"
  billing_mode = "PAY_PER_REQUEST" # Mentalidad Serverless: solo pagas por lo que usas
  hash_key     = "jobId"           # Nuestra Partition Key (PK)

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
  bucket = "extension-s3-uploads-${var.environment}"

  # En local, permitimos que se borre aunque tenga archivos al hacer 'destroy'
  force_destroy = true

  tags = {
    Project = "Nocturne"
  }
}

# 2. La Cola de Mensajes Muertos (DLQ) lambda worker
resource "aws_sqs_queue" "jobs_dlq" {
  name = "extension-sqs-dlq-${var.environment}"
}

# 3. La Cola Principal (conectada a la DLQ) lambda worker
resource "aws_sqs_queue" "jobs_queue" {
  name = "extension-sqs-work-${var.environment}"

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
  name = "extension-worker-role-${var.environment}"

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
  name = "extension-worker-permissions-${var.environment}"
  role = aws_iam_role.worker_role.id # <--- Referencia actualizada

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Sid = "AllowLogging"
        # Permiso para escribir logs (Observabilidad)
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Effect   = "Allow"
        Resource = "arn:aws:logs:*:*:*"
      },
      { Sid = "AllowS3Read"
        # Permiso para el Bunker S3
        Action   = ["s3:GetObject"]
        Effect   = "Allow"
        Resource = "${aws_s3_bucket.uploads_bucket.arn}/*"
      },
      { Sid = "AllowDynamoWrite"
        # Permiso para el Cerebro DynamoDB
        Action   = ["dynamodb:UpdateItem", "dynamodb:GetItem"]
        Effect   = "Allow"
        Resource = aws_dynamodb_table.jobs_table.arn
      },
      # --- NUEVO PERMISO: DESCIFRADO ---
      { Sid      = "AllowKMSDecrypt"
        Action   = ["kms:Decrypt"]
        Effect   = "Allow"
        Resource = aws_kms_key.token_key.arn
      },

      #ACTUALIZACIÓN DE PERMISOS (Añadir SQS SendMessage)
      {
        Sid      = "AllowSQSReplay"
        Action   = ["sqs:SendMessage"]
        Effect   = "Allow"
        Resource = aws_sqs_queue.jobs_queue.arn
      },
      # --- NUEVO: PERMISO PARA SECRETOS DE GOOGLE ---
      {
        Sid    = "AllowSSMRead"
        Action = ["ssm:GetParameter"]
        Effect = "Allow"
        Resource = [
          aws_ssm_parameter.google_client_id.arn,
          aws_ssm_parameter.google_client_secret.arn
        ]
      }
    ]
  })
}

# =============================================================================
# 2. EMPAQUETADO: CREACIÓN AUTOMÁTICA DEL ZIP
# =============================================================================

# Terraform genera el ZIP por nosotros.
# NOTA: Para que esto funcione, las dependencias deben estar en la carpeta dist/lambda
#data "archive_file" "lambda_zip" {
# type        = "zip"
#source_dir  = "${path.module}/../../../dist/lambda"
#output_path = "${path.module}/../../../dist/worker.zip"
#}

# =============================================================================
# 3. COMPUTACIÓN: LA FUNCIÓN LAMBDA WORKER DE MOMENTO
# =============================================================================

resource "aws_lambda_function" "worker_lambda" {
  function_name    = "extension-worker-${var.environment}"
  filename         = "${path.module}/../../../dist/worker.zip"
  source_code_hash = filebase64sha256("${path.module}/../../../dist/worker.zip")

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
      SQS_QUEUE_URL    = aws_sqs_queue.jobs_queue.url       # <--- NUEVA VARIABLE
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
          #AWS = "arn:aws:iam::000000000000:root" # En AWS real sería tu cuenta
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"

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
# 6. CONFIGURACIÓN: GOOGLE API SECRETS (SSM)
# =============================================================================

resource "aws_ssm_parameter" "google_client_id" {
  name  = "/extension/google/client_id"
  type  = "String"     # En AWS real usaríamos 'SecureString'
  value = "REPLACE_ME" # Lo llenaremos vía CLI o .env
  # ESTO ES VITAL:Crea el parámetro la primera vez, pero después ignora si el valor cambia asi ejecutes 100 veces
  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "google_client_secret" {
  name  = "/extension/google/client_secret"
  type  = "String"
  value = "REPLACE_ME"
  # ESTO ES VITAL:Crea el parámetro la primera vez, pero después ignora si el valor cambia asi ejecutes 100 veces
  lifecycle {
    ignore_changes = [value]
  }
}

# =============================================================================
# 7. DISPATCHER: ROL Y PERMISOS LAMBDA DISPATCHER
# =============================================================================

resource "aws_iam_role" "dispatcher_role" {
  name = "extension-dispatcher-role-${var.environment}"

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

resource "aws_iam_role_policy" "dispatcher_permissions" {
  name = "extension-dispatcher-permissions-${var.environment}"
  role = aws_iam_role.dispatcher_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AllowLogging"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Effect   = "Allow"
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Sid = "AllowDynamoAccess"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:GetItem",
          "dynamodb:Query" # Para buscar si el usuario ya tiene un Job activo
        ]
        Effect   = "Allow"
        Resource = aws_dynamodb_table.jobs_table.arn
      },
      {
        Sid      = "AllowSQSSend"
        Action   = ["sqs:SendMessage"]
        Effect   = "Allow"
        Resource = aws_sqs_queue.jobs_queue.arn
      },
      {
        Sid = "AllowIngestionConsume"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Effect   = "Allow"
        Resource = aws_sqs_queue.ingestion_queue.arn
      }
    ]
  })
}

# =============================================================================
# 8. DISPATCHER: EMPAQUETADO Y FUNCIÓN CREACION LAMBDA
# =============================================================================

# Generamos un ZIP específico para el Dispatcher
# Nota: Crearemos la carpeta dist/dispatcher en el siguiente paso de Python
#data "archive_file" "dispatcher_zip" {
# type        = "zip"
# source_dir  = "${path.module}/../../../dist/dispatcher"
#output_path = "${path.module}/../../../dist/dispatcher.zip"
#}

resource "aws_lambda_function" "dispatcher_lambda" {
  function_name    = "extension-dispatcher-${var.environment}"
  filename         = "${path.module}/../../../dist/dispatcher.zip"
  source_code_hash = filebase64sha256("${path.module}/../../../dist/dispatcher.zip")

  handler = "dispatcher.lambda_handler" # El archivo se llamará dispatcher.py
  runtime = "python3.12"
  timeout = 10 # El Dispatcher debe ser rápido
  role    = aws_iam_role.dispatcher_role.arn

  environment {
    variables = {
      DYNAMODB_TABLE = aws_dynamodb_table.jobs_table.name
      SQS_QUEUE_URL  = aws_sqs_queue.jobs_queue.url
      ENVIRONMENT    = var.environment
    }
  }
}

#IMPORTANTE
# PERMISO: Permitir que S3 invoque a esta Lambda
resource "aws_lambda_permission" "allow_s3_to_call_dispatcher" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.dispatcher_lambda.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.uploads_bucket.arn
}

#cola sqs entre s3---->sqs---->distpacher
# 1. DLQ para la Ingesta (El cementerio de eventos de S3)
resource "aws_sqs_queue" "ingestion_dlq" {
  name = "extension-sqs-ingestion-dlq-${var.environment}"
}

# 2. Cola de Ingesta Principal sqs entre s3---->sqs---->distpacher
resource "aws_sqs_queue" "ingestion_queue" {
  name = "extension-sqs-ingestion-${var.environment}"

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.ingestion_dlq.arn
    maxReceiveCount     = 3
  })
}

# 3. POLÍTICA DE ACCESO: Permite que S3 escriba en esta cola
resource "aws_sqs_queue_policy" "ingestion_queue_policy" {
  queue_url = aws_sqs_queue.ingestion_queue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "s3.amazonaws.com" }
        Action    = "sqs:SendMessage"
        Resource  = aws_sqs_queue.ingestion_queue.arn
        Condition = {
          ArnLike = { "aws:SourceArn" : aws_s3_bucket.uploads_bucket.arn }
        }
      }
    ]
  })
}

# =============================================================================
# 9. CONECTAMOS EVENTOS: CONEXIÓN S3 -> SQS
# =============================================================================
#
resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = aws_s3_bucket.uploads_bucket.id

  queue {
    queue_arn     = aws_sqs_queue.ingestion_queue.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "uploads/"
    filter_suffix = ".json"
  }

  # IMPORTANTE: S3 necesita que la política de la cola exista antes de probar la conexión
  depends_on = [aws_sqs_queue_policy.ingestion_queue_policy]
}
#Y LUEGO onectamos la cola con la Lambda Dispatcher.

resource "aws_lambda_event_source_mapping" "ingestion_trigger" {
  event_source_arn = aws_sqs_queue.ingestion_queue.arn
  function_name    = aws_lambda_function.dispatcher_lambda.arn
  batch_size       = 1 # Procesamos de 1 en 1 para máxima trazabilidad
  enabled          = true
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
