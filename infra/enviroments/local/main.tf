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
