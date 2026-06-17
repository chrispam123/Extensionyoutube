import os
import json  # <--- ESTA ES LA PIEZA QUE FALTA


def get_cors_headers():
    # Obtenemos el ID de la variable de entorno que inyecta Terraform
    ext_id = os.getenv("EXTENSION_ID", "*")
    origin = f"chrome-extension://{ext_id}" if ext_id != "*" else "*"

    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Max-Age": "3600",
    }


def cors_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            **get_cors_headers(),  # Fusionamos con las cabeceras CORS
        },
        "body": json.dumps(body),
    }
