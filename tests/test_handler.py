import boto3
import pytest
from moto import mock_aws
from src.worker.handler import lambda_handler


@mock_aws
def test_handler_success():
    # 1. PREPARAR (Simulamos AWS en memoria)
    s3 = boto3.client("s3", region_name="us-east-1")
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

    # Creamos el bucket y la tabla de mentira
    s3.create_bucket(Bucket="nocturne-s3-uploads-local")
    table = dynamodb.create_table(
        TableName="nocturne-dynamo-jobs-local",
        KeySchema=[{"AttributeName": "jobId", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "jobId", "AttributeType": "S"}],
        ProvisionedThroughput={"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
    )

    # Ponemos un archivo de prueba en el S3 de mentira
    s3.put_object(
        Bucket="nocturne-s3-uploads-local",
        Key="uploads/user-1/job-1.json",
        Body='[{"id": "chan1", "title": "Test Channel"}]',
    )

    # Creamos el registro inicial en DynamoDB
    table.put_item(Item={"jobId": "job-1", "status": "PENDING"})

    # 2. ACTUAR (Llamamos a la función)
    event = {"Records": [{"body": '{"jobId": "job-1", "userId": "user-1"}'}]}
    response = lambda_handler(event, None)

    # 3. VERIFICAR
    assert response["status"] == "processed"

    # Verificamos que en DynamoDB ahora diga DONE
    item = table.get_item(Key={"jobId": "job-1"})["Item"]
    assert item["status"] == "DONE"
