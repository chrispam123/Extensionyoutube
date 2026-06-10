# -*- coding: utf-8 -*-
"""
Shared Security Module
Purpose: Handle KMS encryption/decryption with Base64 safety.
"""

import base64
import os
from aws_lambda_powertools import Logger

logger = Logger()


def decrypt_token(kms_client, ciphertext_b64: str) -> str:
    """
    Toma un string en Base64, lo descifra con KMS y devuelve el texto plano.
    """
    try:
        # 1. Convertir el texto Base64 de DynamoDB a bytes binarios
        ciphertext_bytes = base64.b64decode(ciphertext_b64)

        # 2. Llamar a KMS para descifrar
        # Nota: No pasamos KeyId porque el Ciphertext ya tiene el ID de la llave incrustado
        response = kms_client.decrypt(CiphertextBlob=ciphertext_bytes)

        # 3. Devolver el resultado como string de texto
        return response["Plaintext"].decode("utf-8")

    except Exception as e:
        logger.error(f"Error al descifrar con KMS: {str(e)}")
        raise e
