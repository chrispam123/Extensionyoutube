# -*- coding: utf-8 -*-
import json
import os
import uuid
import boto3
from aws_lambda_powertools import Logger, Tracer
from shared.responses import cors_response, get_cors_headers
from shared.auth import decode_nocturne_jwt

logger = Logger()
tracer = Tracer()

# Clientes AWS (Warm Start)
ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")
if not ENDPOINT_URL or not ENDPOINT_URL.strip():
    ENDPOINT_URL = None

ssm = boto3.client("ssm", endpoint_url=ENDPOINT_URL)
dynamo = boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL)
sqs = boto3.client("sqs", endpoint_url=ENDPOINT_URL)


def lambda_handler(event, context):
    # 1. Guardia CORS
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return {"statusCode": 200, "headers": get_cors_headers()}

    table = dynamo.Table(os.getenv("DYNAMODB_TABLE"))

    try:
        # 2. VALIDACIÓN DE IDENTIDAD (401)
        auth_header = event.get("headers", {}).get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return cors_response(401, {"error": "No autorizado"})

        token = auth_header.split(" ")[1]

        # Recuperamos el secreto de firma desde SSM
        jwt_secret = ssm.get_parameter(
            Name="/extension/auth/jwt_secret", WithDecryption=True
        )["Parameter"]["Value"]

        try:
            decoded = decode_nocturne_jwt(token, jwt_secret)
            user_id = decoded["sub"]  # Identidad real extraída del token
        except Exception as e:
            logger.warning(f"Token inválido: {str(e)}")
            return cors_response(401, {"error": "Sesión expirada o inválida"})

        # 3. CHECK DE TRABAJOS ACTIVOS (409)
        # Buscamos en el 'cajón' del usuario (PK) cualquier Job (SK empieza por JOB#)
        active_jobs = table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
            ExpressionAttributeValues={":pk": f"USER#{user_id}", ":sk": "JOB#"},
        )

        # Filtramos si hay alguno que no esté en estado final (DONE/FAILED) 409 no es un "fallo", sino una forma de recuperar la sesión
        for job in active_jobs.get("Items", []):
            if job.get("status") in [
                "INITIALIZING",
                "PENDING",
                "RUNNING",
                "PAUSED_QUOTA",
            ]:
                logger.info(
                    f"Conflicto: Usuario {user_id} ya tiene el Job {job['jobId']} activo"
                )
                return cors_response(
                    409,
                    {
                        "error": "Ya tienes un proceso en marcha",
                        "jobId": job.get("jobId"),
                    },
                )

        # 4. CREACIÓN DE NUEVO TRABAJO (EXPORT)
        job_id = str(uuid.uuid4())
        body = json.loads(event.get("body", "{}"))
        job_type = body.get("type", "EXPORT").upper()

        logger.info(f"Creando nuevo Job {job_id} para {user_id}")

        # Registro en DynamoDB (Single Table Design)
        table.put_item(
            Item={
                "PK": f"USER#{user_id}",
                "SK": f"JOB#{job_id}",
                "jobId": job_id,
                "userId": user_id,
                "type": job_type,
                "status": "PENDING",
                "doneCount": 0,
                "createdAt": str(datetime.datetime.utcnow()),
            }
        )

        # 5. DISPARO ASÍNCRONO
        sqs.send_message(
            QueueUrl=os.getenv("SQS_QUEUE_URL"),
            MessageBody=json.dumps(
                {"jobId": job_id, "userId": user_id, "type": job_type}
            ),
        )

        return cors_response(201, {"jobId": job_id, "status": "PENDING"})

    except Exception as e:
        logger.exception("Error en el Iniciador")
        return cors_response(500, {"error": "Internal Server Error"})
