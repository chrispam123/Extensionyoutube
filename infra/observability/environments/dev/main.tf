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
      ENVIRONMENT         = var.environment
      OBSERVED_COMPONENTS = join(",", var.observed_components)
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
