import boto3
import pytest
import json
from moto import mock_aws
from src.worker.handler import lambda_handler


# 1. Definimos el "Doble de Acción" para el contexto de AWS
class MockContext:
    def __init__(self):
        self.function_name = "nocturne-worker-local"
        self.memory_limit_in_mb = "128"
        self.invoked_function_arn = (
            "arn:aws:lambda:us-east-1:000000000000:function:nocturne-worker-local"
        )
        self.aws_request_id = "test-request-id"


@mock_aws
def test_handler_success():
    # 2. Configuración del entorno simulado
    s3 = boto3.client("s3", region_name="us-east-1")
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

    s3.create_bucket(Bucket="nocturne-s3-uploads-local")
    table = dynamodb.create_table(
        TableName="nocturne-dynamo-jobs-local",
        KeySchema=[{"AttributeName": "jobId", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "jobId", "AttributeType": "S"}],
        ProvisionedThroughput={"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
    )

    # Datos de prueba
    job_id = "job-1"
    user_id = "user-1"
    s3.put_object(
        Bucket="nocturne-s3-uploads-local",
        Key=f"uploads/{user_id}/{job_id}.json",
        Body=json.dumps([{"id": "chan1", "title": "Test"}]),
    )
    table.put_item(Item={"jobId": job_id, "status": "PENDING"})

    # 3. EL DISPARO (Aquí pasamos el MockContext en lugar de None)
    event = {"Records": [{"body": json.dumps({"jobId": job_id, "userId": user_id})}]}

    # ¡ATENCIÓN AQUÍ! Pasamos una instancia de MockContext()
    response = lambda_handler(event, MockContext())

    # 4. Verificación
    assert response["status"] == "processed"
    item = table.get_item(Key={"jobId": job_id})["Item"]
    assert item["status"] == "DONE"
