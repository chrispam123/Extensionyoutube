# -*- coding: utf-8 -*-
import datetime
import os

import jwt


def create_nocturne_jwt(user_id: str, email: str, secret: str) -> str:
    """
    Genera un token firmado para la sesión de la extensión.
    """
    payload = {
        "sub": user_id,
        "email": email,
        "iat": datetime.datetime.utcnow(),
        "exp": datetime.datetime.utcnow()
        + datetime.timedelta(days=7),  # Expira en 7 días el token JWT
    }

    # Algoritmo HS256: Simétrico, usa el JWT_SECRET de SSM
    return jwt.encode(payload, secret, algorithm="HS256")


# necesita saber si el token es legítimo. Añadiremos la función decode_nocturne_jwt.
def decode_nocturne_jwt(token: str, secret: str) -> dict:
    """
    Valida la firma y extrae los datos del token.
    Lanza excepciones si el token es inválido o ha expirado.
    """
    # jwt.decode verifica automáticamente la firma y la fecha 'exp'
    return jwt.decode(token, secret, algorithms=["HS256"])
