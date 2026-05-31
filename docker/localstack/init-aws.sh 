#!/bin/bash
echo "########### Initializing LocalStack Resources ###########"

# 1. Crear SQS Dead Letter Queue
awslocal sqs create-queue --queue-name nocturne-sqs-dlq-local

# 2. Crear SQS Main Queue (con Redrive Policy hacia la DLQ)
# Nota: El ARN en LocalStack sigue un patrón predecible
awslocal sqs create-queue --queue-name nocturne-sqs-main-local \
    --attributes '{
      "RedrivePolicy": "{\"deadLetterTargetArn\":\"arn:aws:sqs:us-east-1:000000000000:nocturne-sqs-dlq-local\",\"maxReceiveCount\":\"3\"}"
    }'

# 3. Crear Tabla DynamoDB
# Usamos jobId como Partition Key (HASH)
awslocal dynamodb create-table \
    --table-name nocturne-dynamo-jobs-local \
    --attribute-definitions AttributeName=jobId,AttributeType=S \
    --key-schema AttributeName=jobId,KeyType=HASH \
    --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5

# 4. Crear Bucket S3
awslocal s3 mb s3://nocturne-s3-uploads-local

echo "########### Resources Created Successfully ###########"
