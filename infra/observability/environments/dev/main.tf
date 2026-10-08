data "aws_dynamodb_table" "jobs" {
  name = "extension-dynamo-table-${var.environment}"
}

data "aws_apigatewayv2_api" "http" {
  api_id = var.api_gateway_id
}

data "aws_s3_bucket" "uploads" {
  bucket = "extension-s3-uploads-${var.environment}"
}

data "aws_caller_identity" "current" {}

data "archive_file" "observability_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../../../../observability/backend"
  output_path = "${path.module}/../../../../dist/observability.zip"
  excludes    = ["**/__pycache__/**", "**/*.pyc"]
}

resource "aws_iam_role" "observability_lambda" {
  name = "extension-observability-role-${var.environment}"

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

  tags = {
    Project     = "Nocturne"
    Environment = var.environment
    Component   = "Observability"
  }
}

resource "aws_iam_role_policy" "observability_lambda" {
  name = "extension-observability-permissions-${var.environment}"
  role = aws_iam_role.observability_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadLambdaMetrics"
        Effect   = "Allow"
        Action   = ["cloudwatch:GetMetricData"]
        Resource = "*"
      },
      {
        Sid    = "WriteOwnLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.observability.arn}:*"
      },
      {
        Sid    = "ReadJobStatus"
        Effect = "Allow"
        Action = ["dynamodb:Query"]
        Resource = [
          data.aws_dynamodb_table.jobs.arn,
          "${data.aws_dynamodb_table.jobs.arn}/index/StatusIndex"
        ]
      },
      {
        Sid      = "ReadExportObjects"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${data.aws_s3_bucket.uploads.arn}/exports/*"
      },
      {
        Sid    = "ReadEventBridgeRule"
        Effect = "Allow"
        Action = [
          "events:DescribeRule",
          "events:ListTargetsByRule"
        ]
        Resource = "arn:aws:events:${var.aws_region}:${data.aws_caller_identity.current.account_id}:rule/${var.eventbridge_rule_name}"
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "observability" {
  name              = "/aws/lambda/extension-observability-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = {
    Project     = "Nocturne"
    Environment = var.environment
    Component   = "Observability"
  }
}

resource "aws_lambda_function" "observability" {
  function_name    = "extension-observability-${var.environment}"
  filename         = data.archive_file.observability_lambda.output_path
  source_code_hash = data.archive_file.observability_lambda.output_base64sha256

  handler     = "handler.lambda_handler"
  runtime     = "python3.12"
  memory_size = 128
  timeout     = 15
  role        = aws_iam_role.observability_lambda.arn

  environment {
    variables = {
      ENVIRONMENT                 = var.environment
      OBSERVED_COMPONENTS         = join(",", var.observed_components)
      OBSERVED_QUEUES             = join(",", var.observed_queues)
      DYNAMODB_TABLE              = data.aws_dynamodb_table.jobs.name
      API_GATEWAY_ID              = data.aws_apigatewayv2_api.http.id
      API_GATEWAY_STAGE           = var.api_gateway_stage
      S3_BUCKET                   = data.aws_s3_bucket.uploads.id
      EVENTBRIDGE_RULE_NAME       = var.eventbridge_rule_name
      EVENTBRIDGE_TARGET_FUNCTION = var.eventbridge_target_function
    }
  }

  depends_on = [
    aws_iam_role_policy.observability_lambda,
    aws_cloudwatch_log_group.observability
  ]

  tags = {
    Project     = "Nocturne"
    Environment = var.environment
    Component   = "Observability"
  }
}

resource "aws_apigatewayv2_api" "observability" {
  name          = "extension-observability-api-${var.environment}"
  protocol_type = "HTTP"

  tags = {
    Project     = "Nocturne"
    Environment = var.environment
    Component   = "Observability"
  }
}

resource "aws_apigatewayv2_stage" "observability" {
  api_id      = aws_apigatewayv2_api.observability.id
  name        = var.environment
  auto_deploy = true

  tags = {
    Project     = "Nocturne"
    Environment = var.environment
    Component   = "Observability"
  }
}

resource "aws_apigatewayv2_integration" "observability" {
  api_id                 = aws_apigatewayv2_api.observability.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.observability.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "observability" {
  api_id             = aws_apigatewayv2_api.observability.id
  route_key          = "GET /observability"
  target             = "integrations/${aws_apigatewayv2_integration.observability.id}"
  authorization_type = "AWS_IAM"
}

resource "aws_lambda_permission" "observability_api" {
  statement_id  = "AllowExecutionFromObservabilityAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.observability.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.observability.execution_arn}/*/GET/observability"
}

resource "aws_cognito_user_pool" "observability" {
  name                = "extension-observability-${var.environment}"
  username_attributes = ["email"]
  auto_verified_attributes = [
    "email"
  ]

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 7
  }

  tags = {
    Project     = "Nocturne"
    Environment = var.environment
    Component   = "Observability"
  }
}

resource "aws_cognito_user_pool_domain" "observability" {
  domain       = var.cognito_domain_prefix
  user_pool_id = aws_cognito_user_pool.observability.id
}

resource "aws_cognito_identity_provider" "google" {
  user_pool_id  = aws_cognito_user_pool.observability.id
  provider_name = "Google"
  provider_type = "Google"

  provider_details = {
    client_id        = var.google_client_id
    client_secret    = var.google_client_secret
    authorize_scopes = "openid email profile"
  }

  attribute_mapping = {
    email = "email"
  }
}

resource "aws_cognito_user_pool_client" "observability" {
  name         = "extension-observability-client-${var.environment}"
  user_pool_id = aws_cognito_user_pool.observability.id

  generate_secret = false

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO", "Google"]

  callback_urls = var.cognito_callback_urls
  logout_urls   = var.cognito_logout_urls

  depends_on = [aws_cognito_identity_provider.google]

  explicit_auth_flows = [
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH"
  ]
}
