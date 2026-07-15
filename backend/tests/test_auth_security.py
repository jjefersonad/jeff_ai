"""Testes de `src/infrastructure/auth/security.py` (hash e verificação de senha)."""
from __future__ import annotations

from src.infrastructure.auth import security


def test_get_password_hash_does_not_return_plaintext() -> None:
    hashed = security.get_password_hash("correct horse battery staple")

    assert hashed != "correct horse battery staple"
    assert hashed.startswith("$2b$")


def test_verify_password_accepts_matching_password() -> None:
    hashed = security.get_password_hash("s3cr3t")

    assert security.verify_password("s3cr3t", hashed) is True


def test_verify_password_rejects_wrong_password() -> None:
    hashed = security.get_password_hash("s3cr3t")

    assert security.verify_password("wrong", hashed) is False


def test_get_password_hash_uses_bcrypt_and_salts_each_call() -> None:
    first = security.get_password_hash("s3cr3t")
    second = security.get_password_hash("s3cr3t")

    assert first != second
