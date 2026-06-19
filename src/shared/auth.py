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
        + datetime.timedelta(days=7),  # Expira en 7 días
    }

    # Algoritmo HS256: Simétrico, usa el JWT_SECRET de SSM
    return jwt.encode(payload, secret, algorithm="HS256")
