# -*- coding: utf-8 -*-
import json
import os
import uuid
import boto3
import datetime
from aws_lambda_powertools import Logger, Tracer
from shared.responses import cors_response, get_cors_headers
from shared.auth import decode_nocturne_jwt

# 1. Configuración de Observabilidad
logger = Logger()
tracer = Tracer()

# 2. Inicialización de Clientes (Warm Start)
RAW_ENDPOINT = os.getenv("AWS_ENDPOINT_URL")
ENDPOINT_URL = RAW_ENDPOINT if RAW_ENDPOINT and RAW_ENDPOINT.strip() else None

ssm = boto3.client("ssm", endpoint_url=ENDPOINT_URL)
dynamo = boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL)
sqs = boto3.client("sqs", endpoint_url=ENDPOINT_URL)
s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL)


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    # --- GUARDIA CORS (OPTIONS) ---
    method = event.get("requestContext", {}).get("http", {}).get("method")
    if method == "OPTIONS":
        return {"statusCode": 200, "headers": get_cors_headers()}

    table = dynamo.Table(os.getenv("DYNAMODB_TABLE"))

    try:
        # 3. VALIDACIÓN DE IDENTIDAD
        logger.info("🔐 Validando identidad del usuario...")
        auth_header = event.get("headers", {}).get("authorization", "")
        if not auth_header.startswith("Bearer "):
            logger.warning("⚠️ Petición sin cabecera de autorización válida")
            return cors_response(401, {"error": "No autorizado"})

        token = auth_header.split(" ")[1]

        # Recuperamos el secreto de firma (Aquí es donde necesitamos el permiso de SSM)
        logger.info("🔍 Recuperando JWT_SECRET desde SSM...")
        jwt_secret = ssm.get_parameter(
            Name="/extension/auth/jwt_secret", WithDecryption=True
        )["Parameter"]["Value"]

        try:
            decoded = decode_nocturne_jwt(token, jwt_secret)
            user_id = decoded["sub"]
            logger.info(f"👤 Usuario identificado: {user_id}")
        except Exception as e:
            logger.warning(f"❌ Token inválido o expirado: {str(e)}")
            return cors_response(401, {"error": "Sesión inválida"})

        # 4. CHECK DE TRABAJOS ACTIVOS (Idempotencia)
        logger.info(f"🔎 Buscando trabajos activos para el usuario {user_id}...")
        active_jobs = table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
            ExpressionAttributeValues={":pk": f"USER#{user_id}", ":sk": "JOB#"},
        )

        for job in active_jobs.get("Items", []):
            if job.get("status") in [
                "INITIALIZING",
                "PENDING",
                "RUNNING",
                "PAUSED_QUOTA",
            ]:
                logger.info(
                    f"🚫 Conflicto detectado: Job {job['jobId']} ya está activo."
                )
                return cors_response(
                    409,
                    {
                        "error": "Ya tienes un proceso en marcha",
                        "jobId": job.get("jobId"),
                    },
                )

        # 5. CREACIÓN DE NUEVO TRABAJO
        job_id = str(uuid.uuid4())
        body = json.loads(event.get("body", "{}"))
        job_type = body.get("type", "EXPORT").upper()

        initial_status = "INITIALIZING" if job_type == "IMPORT" else "PENDING"
        logger.info(f"🆕 Creando nuevo Job {job_id} de tipo {job_type}")

        # Registro en DynamoDB
        table.put_item(
            Item={
                "PK": f"USER#{user_id}",
                "SK": f"JOB#{job_id}",
                "jobId": job_id,
                "userId": user_id,
                "type": job_type,
                "status": initial_status,
                "doneCount": 0,
                "createdAt": datetime.datetime.now(datetime.UTC).isoformat(),
            }
        )

        # 6. BIFURCACIÓN DE FLUJO
        response_data = {"jobId": job_id, "type": job_type}

        if job_type == "IMPORT":
            logger.info(
                f"📦 Generando Presigned URL para importación en Job {job_id}..."
            )
            s3_key = f"uploads/{user_id}/{job_id}.json"
            upload_url = s3.generate_presigned_url(
                ClientMethod="put_object",
                Params={
                    "Bucket": os.getenv("S3_BUCKET"),
                    "Key": s3_key,
                    "ContentType": "application/json",
                },
                ExpiresIn=300,
            )
            response_data["uploadUrl"] = upload_url
        else:
            logger.info(f"🚀 Enviando orden de exportación a SQS para Job {job_id}...")
            sqs.send_message(
                QueueUrl=os.getenv("SQS_QUEUE_URL"),
                MessageBody=json.dumps(
                    {"jobId": job_id, "userId": user_id, "type": job_type}
                ),
            )

        logger.info(f"✅ Job {job_id} iniciado con éxito.")
        return cors_response(201, response_data)

    except Exception as e:
        logger.exception(f"🔥 Error crítico en el Iniciador: {str(e)}")
        return cors_response(500, {"error": "Internal Server Error"})
