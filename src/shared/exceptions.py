# -*- coding: utf-8 -*-
"""
Shared Exceptions Module
"""


class NocturneError(Exception):
    """Base para todos los errores de Nocturne"""

    pass


class QuotaExceededError(NocturneError):
    """Se lanza cuando YouTube responde con error 403: quotaExceeded"""

    pass


class InvalidTokenError(NocturneError):
    """Se lanza cuando el token de Google ha sido revocado o es inválido"""

    pass
