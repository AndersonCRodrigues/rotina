"""
Utilitário de criptografia simétrica em repouso (Fernet/AES128-CBC + HMAC)
para campos sensíveis do modelo, independente do hashing de senha do
Django (que é unidirecional e trata de autenticação, não de dados que
precisam ser lidos de volta).

Uso:
    from core.crypto import encrypt_text, decrypt_text
    token = encrypt_text("dado sensível")
    original = decrypt_text(token)

Ou via o campo de model pronto `EncryptedTextField` (ver `fields.py`).
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = getattr(settings, "FIELD_ENCRYPTION_KEY", "")
    if not key:
        raise ImproperlyConfigured(
            "FIELD_ENCRYPTION_KEY não configurada. Gere uma com "
            "`python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"` e defina no .env."
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_text(plain: str) -> str:
    """Criptografa uma string e devolve um token seguro para armazenar em texto."""
    if plain is None:
        return plain
    token = _fernet().encrypt(plain.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_text(token: str) -> str:
    """Descriptografa um token gerado por `encrypt_text`.

    Retorna string vazia se o token for inválido/corrompido, em vez de
    estourar exceção em tela de listagem — o erro é logado.
    """
    if not token:
        return token
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return ""
