# El robot se mira al espejo para saber su ID de cuenta real
data "aws_caller_identity" "current" {}
#si estás construyendo un sistema escalable. Aunque requiere más esfuerzo inicial para programar las consultas,
# te da toda la flexibilidad necesaria para hacer búsquedas por estado gracias al GSI y te permite
# hacer crecer tu base de datos sin crear tablas nuevas.
resource "aws_dynamodb_table" "jobs_table" {
  name         = "extension-dynamo-table-${var.environment}"
  billing_mode = "PAY_PER_REQUEST" # Mentalidad Serverless: solo pagas por lo que usas
  #hash_key     = "jobId"           # Nuestra Partition Key (PK)
  hash_key  = "PK" # Partition Key genérica
  range_key = "SK" # Sort Key genérica
  #attribute {
  # name = "jobId"
  # type = "S" # String
  #}
  #
  # --- NUEVO: ACTIVAR EL RELOJ DE LIMPIEZA ---
  ttl {
    attribute_name = "expiresAt" # DynamoDB mirará este campo
    enabled        = true
  }

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  # Mantenemos el GSI para el Resumer, pero ahora sobre el campo 'status'
  # Nota: Para usar un GSI, el atributo debe estar definido arriba
  attribute {
    name = "status"
    type = "S"
  }

  global_secondary_index {
    name            = "StatusIndex"
    hash_key        = "status"
    range_key       = "PK"
    projection_type = "ALL"
  }


  tags = {
    Project     = "Nocturne"
    Environment = "develop"
  }


}


# 1. El Bunker S3 donde se suben los canales y playslits EXPORTADOS
resource "aws_s3_bucket" "uploads_bucket" {
  bucket = "extension-s3-uploads-${var.environment}"

  # En local, permitimos que se borre aunque tenga archivos al hacer 'destroy'
  force_destroy = true

  tags = {
    Project = "Nocturne"
  }
}

# 2. POLÍTICA DE CICLO DE VIDA PARA S3 (Higiene Automática)
# Eliminamos archivos antiguos de S3 para evitar acumulación de datos
resource "aws_s3_bucket_lifecycle_configuration" "uploads_lifecycle" {
  bucket = aws_s3_bucket.uploads_bucket.id
  rule {
    id     = "cleanup-exports"
    status = "Enabled"

    filter {
      prefix = "exports/" # Solo afecta a las exportaciones terminadas
    }

    expiration {
      days = 7 # Los archivos mueren automáticamente tras una semana
    }
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

#Permites que esta extensión te suba un archivo?".
# Si S3 no tiene una política de CORS, bloqueará la subida aunque la URL sea válida.
resource "aws_s3_bucket_cors_configuration" "uploads_cors" {
  bucket = aws_s3_bucket.uploads_bucket.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT"] # Solo permitimos subidas
    allowed_origins = ["chrome-extension://${var.extension_id}"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

# =============================================================================
# 1. SEGURIDAD: ROL DE IAM PARA LA LAMBDA WORKER
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
      { # Actualizamos el bloque de S3
        Sid    = "AllowS3BucketLevel"
        Action = ["s3:ListBucket"]
        Effect = "Allow"
        # OJO: Aquí NO lleva /* al final, apunta al cubo directamente arn:aws:s3:::mi-bucket -> Es la caja.
        # Para que el Worker pueda manejar el error NoSuchKey (404) y saber que debe empezar una lista vacía, necesita ver la caja.
        Resource = aws_s3_bucket.uploads_bucket.arn
      },
      {
        Sid    = "AllowS3ObjectLevel"
        Action = ["s3:GetObject", "s3:PutObject"]
        Effect = "Allow"
        # Aquí SÍ lleva /* porque actúa sobre los archivos arn:aws:s3:::mi-bucket/* -> Es lo que hay dentro de la caja.
        Resource = [
          "${aws_s3_bucket.uploads_bucket.arn}/uploads/*",
          "${aws_s3_bucket.uploads_bucket.arn}/exports/*"
        ]
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

      #ACTUALIZACIÓN DE PERMISOS (Añadir SQS SendMessage) es el permiso para HABLAR (enviar mensajes).
      # Es lo que el Worker usa para el "Relay" (auto-invocación).
      {
        Sid      = "AllowSQSReplay"
        Action   = ["sqs:SendMessage"]
        Effect   = "Allow"
        Resource = aws_sqs_queue.jobs_queue.arn
      },
      #El Worker necesita permiso para ESCUCHAR (recibir mensajes).
      # el Event Source Mapping podrá por fin entregarle los mensajes que están acumulados en la cola.
      {
        Sid = "AllowSQSConsume"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
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
# 3. COMPUTACIÓN: LA FUNCIÓN LAMBDA WORKER CREACION
# =============================================================================

resource "aws_lambda_function" "worker_lambda" {
  function_name    = "extension-worker-${var.environment}"
  filename         = "${path.module}/../../../dist/worker.zip"
  source_code_hash = filebase64sha256("${path.module}/../../../dist/worker.zip")

  handler     = "handler.lambda_handler"
  runtime     = "python3.12"
  memory_size = 256                          # Aumentamos para mejor CPU y manejo de JSONs grandes
  timeout     = 60                           # Subimos de 30 a 60 segundos
  role        = aws_iam_role.worker_role.arn # <--- Referencia actualizada


  tracing_config {
    mode = "Active"
  }

  # INYECCIÓN DE DEPENDENCIAS:
  # Terraform pasa los nombres reales de los recursos a la Lambda
  environment {
    variables = {
      AWS_ENDPOINT_URL = var.use_localstack ? "http://localhost.localstack.cloud:4566" : ""
      S3_BUCKET        = aws_s3_bucket.uploads_bucket.id
      DYNAMODB_TABLE   = aws_dynamodb_table.jobs_table.name
      KMS_KEY_ALIAS    = aws_kms_alias.token_key_alias.name # <--- INYECCIÓN
      SQS_QUEUE_URL    = aws_sqs_queue.jobs_queue.url       # <--- NUEVA VARIABLEs
    }
  }
}



# =============================================================================
# 4. EVENTOS: CONEXIÓN SQS -> LAMBDA WORKER (TRIGGER)
# =============================================================================

resource "aws_lambda_event_source_mapping" "sqs_trigger" {
  event_source_arn = aws_sqs_queue.jobs_queue.arn
  function_name    = aws_lambda_function.worker_lambda.arn
  batch_size       = 1
  enabled          = true
}

# 1. LA LLAVE MAESTRA KMS
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
  name          = "alias/extension/token-key-${var.environment}"
  target_key_id = aws_kms_key.token_key.key_id
}




# =============================================================================
# 6. CONFIGURACIÓN: GOOGLE API SECRETS (SSM)
# =============================================================================

resource "aws_ssm_parameter" "google_client_id" {
  # Añadimos el environment a la ruta: /extension/develop/... o /extension/prod/...
  name  = "/extension/${var.environment}/google/client_id"
  type  = "String"     # En AWS real usaríamos 'SecureString'
  value = "REPLACE_ME" # Lo llenaremos vía CLI o .env
  # ESTO ES VITAL:Crea el parámetro la primera vez, pero después ignora si el valor cambia asi ejecutes 100 veces
  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "google_client_secret" {
  name  = "/extension/${var.environment}/google/client_secret"
  type  = "String"
  value = "REPLACE_ME"
  # ESTO ES VITAL:Crea el parámetro la primera vez, pero después ignora si el valor cambia asi ejecutes 100 veces
  lifecycle {
    ignore_changes = [value]
  }
}

#  SECRETO PARA FIRMAR JWT
resource "aws_ssm_parameter" "jwt_secret" {
  name  = "/extension/${var.environment}/auth/jwt_secret"
  type  = "String" # En prod será SecureString KMS
  value = "REPLACE_ME_WITH_RANDOM_STRING"

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
  tracing_config {
    mode = "Active"
  }
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
# 10. LAMBDA-STATUS: ROL Y PERMISOS (SOLO LECTURA)
# =============================================================================

resource "aws_iam_role" "status_role" {
  name = "extension-status-role-${var.environment}"

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

resource "aws_iam_role_policy" "status_permissions" {
  name = "extension-status-permissions-${var.environment}"
  role = aws_iam_role.status_role.id

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
        Sid      = "AllowDynamoRead"
        Action   = ["dynamodb:GetItem"] # <--- ÚNICO PODER: LEER UN ITEM
        Effect   = "Allow"
        Resource = aws_dynamodb_table.jobs_table.arn
      },
      {
        # AÑADIMOS: Permiso para firmar la descarga
        Sid      = "AllowS3PresignDownload"
        Action   = ["s3:GetObject"]
        Effect   = "Allow"
        Resource = "${aws_s3_bucket.uploads_bucket.arn}/exports/*"
      },

      # --- NUEVO: PERMISO PARA VALIDAR JWT ---
      {
        Sid      = "AllowSSMReadJWTSecret"
        Action   = ["ssm:GetParameter"]
        Effect   = "Allow"
        Resource = aws_ssm_parameter.jwt_secret.arn
      }
    ]
  })
}
# =============================================================================
# 11. CREACION STATUS: FUNCIÓN LAMBDA
# =============================================================================

resource "aws_lambda_function" "status_lambda" {
  function_name    = "extension-status-${var.environment}"
  filename         = "${path.module}/../../../dist/status.zip"
  source_code_hash = filebase64sha256("${path.module}/../../../dist/status.zip")

  handler = "status.lambda_handler"
  runtime = "python3.12"
  timeout = 5 # Consultar DynamoDB es instantáneo
  role    = aws_iam_role.status_role.arn
  tracing_config {
    mode = "Active"
  }
  environment {
    variables = {
      DYNAMODB_TABLE = aws_dynamodb_table.jobs_table.name
      # AQUÍ CONECTAMOS EL PUENTE pra python:
      EXTENSION_ID         = var.extension_id
      POWERTOOLS_LOG_LEVEL = "INFO"
      # --- ESTA ES LA LÍNEA QUE FALTA ---
      S3_BUCKET = aws_s3_bucket.uploads_bucket.id

    }
  }
}

# =============================================================================
# 12. PUERTA DE ENTRADA: API GATEWAY (HTTP API) LA DE SIEMPRE DE AWS APIGATEWAY
# =============================================================================

resource "aws_apigatewayv2_api" "http_api" {
  name          = "extension-api-${var.environment}"
  protocol_type = "HTTP"

  #cors_configuration {
  # Solo permitimos a TU extensión oficial ID DE LA TIENDA CHROME
  #allow_origins = ["chrome-extension://${var.extension_id}"]no deja apigateway httpv2
  # allow_methods = ["GET", "POST", "OPTIONS"]
  # allow_headers = ["content-type", "authorization"]
  #}
}

resource "aws_apigatewayv2_stage" "api_stage" {
  api_id      = aws_apigatewayv2_api.http_api.id
  name        = var.environment
  auto_deploy = true
}

# INTEGRACIÓN: Conecta el API con la Lambda status
resource "aws_apigatewayv2_integration" "status_integration" {
  api_id           = aws_apigatewayv2_api.http_api.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.status_lambda.invoke_arn
}

# RUTA: GET /status/{jobId}
resource "aws_apigatewayv2_route" "status_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /status/{jobId}"
  target    = "integrations/${aws_apigatewayv2_integration.status_integration.id}"
}

# PERMISO: Permite que el API Gateway llame a la Lambda STATUS
resource "aws_lambda_permission" "api_gw" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.status_lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}



# =============================================================================
# 13. UPLOAD: ROL Y PERMISOS LAMBDA UPLOAD
# =============================================================================

resource "aws_iam_role" "upload_role" {
  name = "extension-upload-role-${var.environment}"

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

resource "aws_iam_role_policy" "upload_permissions" {
  name = "extension-upload-permissions-${var.environment}"
  role = aws_iam_role.upload_role.id

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
        Sid      = "AllowDynamoCreateJob"
        Action   = ["dynamodb:PutItem"]
        Effect   = "Allow"
        Resource = aws_dynamodb_table.jobs_table.arn
      },
      {
        Sid      = "AllowS3Presign"
        Action   = ["s3:PutObject"]
        Effect   = "Allow"
        Resource = "${aws_s3_bucket.uploads_bucket.arn}/uploads/*"
      },
      {
        Sid      = "AllowUserJobLookup"
        Action   = ["dynamodb:Query"] #"Dame todo lo que este usuario tenga (PK=USER#123) y luego yo filtro los resultados".
        Effect   = "Allow"
        Resource = aws_dynamodb_table.jobs_table.arn
        # SEGURIDAD NINJA: Solo puede consultar sus propios registros
        # El prefijo de la Partition Key (PK) debe ser USER# seguido del ID del usuario
        Condition = {
          "ForAllValues:StringLike" : {
            "dynamodb:LeadingKeys" : ["USER#*"] #mpediría que esta Lambda consultara los trabajos de un usuario distinto al que está logueado.
          }
        }
      },

      {
        Sid    = "AllowSSMReadJWTSecret"
        Action = ["ssm:GetParameter"]
        Effect = "Allow"
        # Le damos acceso específico al secreto del JWT
        Resource = aws_ssm_parameter.jwt_secret.arn
      },

      # --- NUEVO: PERMISO PARA INICIAR EXPORTACIONES ---ENVIAR A SQS en EXPORTACION
      {
        Sid      = "AllowSQSWorkSend"
        Action   = ["sqs:SendMessage"]
        Effect   = "Allow"
        Resource = aws_sqs_queue.jobs_queue.arn
      }
    ]
  })
}

# =============================================================================
# 14. UPLOAD: FUNCIÓN LAMBDA Y RUTA API
# =============================================================================

resource "aws_lambda_function" "upload_lambda" {
  function_name    = "extension-upload-${var.environment}"
  filename         = "${path.module}/../../../dist/upload.zip"
  source_code_hash = filebase64sha256("${path.module}/../../../dist/upload.zip")

  handler = "upload.lambda_handler"
  runtime = "python3.12"
  timeout = 10
  role    = aws_iam_role.upload_role.arn
  tracing_config {
    mode = "Active"
  }
  environment {
    variables = {
      DYNAMODB_TABLE = aws_dynamodb_table.jobs_table.name
      S3_BUCKET      = aws_s3_bucket.uploads_bucket.id
      SQS_QUEUE_URL  = aws_sqs_queue.jobs_queue.url # <--- NUEVA VARIABLE en la exportacion el mensaje
      # AQUÍ CONECTAMOS EL PUENTE:
      EXTENSION_ID = var.extension_id
    }
  }
}

# INTEGRACIÓN API GATEWAY: POST /jobs con LAMBDA UPLOAD
resource "aws_apigatewayv2_integration" "upload_integration" {
  api_id           = aws_apigatewayv2_api.http_api.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.upload_lambda.invoke_arn
}

resource "aws_apigatewayv2_route" "upload_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /jobs"
  target    = "integrations/${aws_apigatewayv2_integration.upload_integration.id}"
}

# PERMISO: API Gateway -> Upload Lambda
resource "aws_lambda_permission" "api_gw_upload" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.upload_lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

# =============================================================================
# 15. AUTH: ROL Y PERMISOS (EL ADUANERO) LAMBDA AUTH
# =============================================================================

resource "aws_iam_role" "auth_role" {
  name = "extension-auth-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "auth_permissions" {
  name = "extension-auth-permissions-${var.environment}"
  role = aws_iam_role.auth_role.id

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
        Sid    = "AllowSSMReadSecrets"
        Action = ["ssm:GetParameter"]
        Effect = "Allow"
        Resource = [
          aws_ssm_parameter.google_client_id.arn,
          aws_ssm_parameter.google_client_secret.arn,
          aws_ssm_parameter.jwt_secret.arn
        ]
      },
      {
        Sid      = "AllowKMSEncrypt"
        Action   = ["kms:Encrypt"] # <--- SOLO CIFRAR, NO DESCIFRAR cifra JWT que esta guardado en SSM
        Effect   = "Allow"
        Resource = aws_kms_key.token_key.arn
      },
      {
        Sid      = "AllowDynamoUserManagement"
        Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem"]
        Effect   = "Allow"
        Resource = aws_dynamodb_table.jobs_table.arn
        # SEGURIDAD AVANZADA: Solo puede tocar items de usuario
        Condition = {
          "ForAllValues:StringLike" : {
            "dynamodb:LeadingKeys" : ["USER#*"]
          }
        }
      }
    ]
  })
}

# =============================================================================
# LAMBDA AUTH: FUNCIÓN Y RUTA
# =============================================================================

resource "aws_lambda_function" "auth_lambda" {
  function_name    = "extension-auth-${var.environment}"
  filename         = "${path.module}/../../../dist/auth.zip"
  source_code_hash = filebase64sha256("${path.module}/../../../dist/auth.zip")

  handler = "auth_handler.lambda_handler"
  runtime = "python3.12"
  timeout = 15 # El intercambio con Google puede tardar LOGIN ES UN PROCESO ASINCRONO
  role    = aws_iam_role.auth_role.arn

  environment {
    variables = {
      DYNAMODB_TABLE = aws_dynamodb_table.jobs_table.name
      KMS_KEY_ALIAS  = aws_kms_alias.token_key_alias.name
      EXTENSION_ID   = var.extension_id
      # ESTO ACTIVA LOS LOGS DE POWERTOOLS
      POWERTOOLS_LOG_LEVEL = "INFO"
    }
  }
}

# RUTA API GATEWAY: POST /auth/login  frontend---->apigateway--->lambdaAuth
resource "aws_apigatewayv2_integration" "auth_integration" {
  api_id           = aws_apigatewayv2_api.http_api.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.auth_lambda.invoke_arn
}

resource "aws_apigatewayv2_route" "auth_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /auth/login"
  target    = "integrations/${aws_apigatewayv2_integration.auth_integration.id}"
}

resource "aws_lambda_permission" "api_gw_auth" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auth_lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

#LAMBDA RESUMER, ROL Y PERMISOS Y EVENTBRIDGE
resource "aws_iam_role" "resumer_role" {
  name = "extension-resumer-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "resumer_permissions" {
  name = "extension-resumer-permissions-${var.environment}"
  role = aws_iam_role.resumer_role.id

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
        Sid    = "AllowQueryGSI"
        Action = ["dynamodb:Query"]
        Effect = "Allow"
        # IMPORTANTE: El permiso debe incluir el ARN del GSI (termina en /index/StatusIndex)
        Resource = "${aws_dynamodb_table.jobs_table.arn}/index/StatusIndex"
      },
      {
        Sid      = "AllowSQSReactivate"
        Action   = ["sqs:SendMessage"]
        Effect   = "Allow"
        Resource = aws_sqs_queue.jobs_queue.arn
      },
      #Resumer ahora tiene la capacidad de "escribir" en la tabla para que pueda sacar a los Jobs del estado de
      # pausa legalmente
      {
        Sid      = "AllowUpdateTable"
        Action   = ["dynamodb:UpdateItem", "dynamodb:GetItem"]
        Effect   = "Allow"
        Resource = aws_dynamodb_table.jobs_table.arn # Apunta a la tabla, no al índice
      }
    ]
  })
}

# =============================================================================
# 18. RESUMER: FUNCIÓN Y DISPARADOR (EVENTBRIDGE)
# =============================================================================

resource "aws_lambda_function" "resumer_lambda" {
  function_name    = "extension-resumer-${var.environment}"
  filename         = "${path.module}/../../../dist/resumer.zip"
  source_code_hash = filebase64sha256("${path.module}/../../../dist/resumer.zip")

  handler = "resumer.lambda_handler"
  runtime = "python3.12"
  timeout = 30
  role    = aws_iam_role.resumer_role.arn

  environment {
    variables = {
      DYNAMODB_TABLE       = aws_dynamodb_table.jobs_table.name
      SQS_QUEUE_URL        = aws_sqs_queue.jobs_queue.url
      POWERTOOLS_LOG_LEVEL = "INFO"
    }
  }
}

# REGLA CRON: Cada 1 hora
resource "aws_cloudwatch_event_rule" "resumer_cron" {
  name                = "extension-resumer-cron-${var.environment}"
  description         = "Despierta al Resumer cada hora para reanudar jobs pausados"
  schedule_expression = "rate(1 hour)"
}

# DESTINO: Conecta Cron con Lambda
resource "aws_cloudwatch_event_target" "resumer_target" {
  rule      = aws_cloudwatch_event_rule.resumer_cron.name
  target_id = "ResumerLambda"
  arn       = aws_lambda_function.resumer_lambda.arn
}

# PERMISO: Permite que EventBridge llame a la Lambda
resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.resumer_lambda.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.resumer_cron.arn
}


#Xray no es un recurso es un servicio asi se uitliza
# Adjuntar política de X-Ray al rol de lambda Status
resource "aws_iam_role_policy_attachment" "status_xray" {
  role       = aws_iam_role.status_role.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXrayWriteOnlyAccess"
}

# Repite esto para worker_role
resource "aws_iam_role_policy_attachment" "worker_xray" {
  role       = aws_iam_role.worker_role.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXrayWriteOnlyAccess"
}
# Repite esto para upload_role
resource "aws_iam_role_policy_attachment" "upload_xray" {
  role       = aws_iam_role.upload_role.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXrayWriteOnlyAccess"
}
# Repite esto para dispatcher_role
resource "aws_iam_role_policy_attachment" "dispatcher_xray" {
  role       = aws_iam_role.dispatcher_role.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXrayWriteOnlyAccess"
}
# =============================================================================
# 19. CONFIGURACIÓN DE RECURSIVIDAD (Standalone Resource)
# =============================================================================
# --- SOLUCIÓN AL BLOQUEO DE RECURSIVIDAD ---
# Permite que la Lambda se auto-invoque vía SQS más de 16 veces.
# Requiere AWS Provider v5.x
resource "aws_lambda_function_recursion_config" "worker_recursion" {
  function_name  = aws_lambda_function.worker_lambda.function_name
  recursive_loop = "Allow"
}

# OUTPUT: La URL que usará el React
output "api_url" {
  value = "${aws_apigatewayv2_api.http_api.api_endpoint}/${aws_apigatewayv2_stage.api_stage.name}"
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
