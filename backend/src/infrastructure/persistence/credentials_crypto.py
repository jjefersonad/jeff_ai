"""Cifra/decifra simétrica de campos sensíveis de `user_integrations.config`.

Fernet (`cryptography`), chave lida de `INTEGRATION_CREDENTIALS_KEY` (design
Decision 2 de `user-integration-credentials`). Fica na camada de adapter —
importado por `user_integrations_repository.py`, nunca usado diretamente por
um use case (REQ-002 do spec `user-integration-credentials-store`).
"""
from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken

_KEY_ENV_VAR = "INTEGRATION_CREDENTIALS_KEY"


class MissingCredentialsKeyError(RuntimeError):
    """`INTEGRATION_CREDENTIALS_KEY` está ausente ou vazia no ambiente."""


def _fernet() -> Fernet:
    key = os.environ.get(_KEY_ENV_VAR)
    if not key:
        raise MissingCredentialsKeyError(
            f"{_KEY_ENV_VAR} não configurada. Gere uma com "
            "`python -c \"from cryptography.fernet import Fernet; "
            'print(Fernet.generate_key().decode())"` e defina no `.env`.'
        )
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    """Cifra `plaintext`, retornando ciphertext codificado em texto."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decifra `ciphertext` produzido por `encrypt`, retornando o texto original."""
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("ciphertext inválido ou corrompido") from exc
