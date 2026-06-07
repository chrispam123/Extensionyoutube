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
