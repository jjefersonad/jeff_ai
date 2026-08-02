"""Testes de `src/infrastructure/persistence/credentials_crypto.py`.

Cobre a task `user-integration-credentials-task-crypto-1`: cifra/decifra
simétrica (Fernet) de campos sensíveis de `user_integrations.config`
(REQ-002 do spec `user-integration-credentials-store`).
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from src.infrastructure.persistence import credentials_crypto as crypto

_VALID_KEY = Fernet.generate_key().decode()


def test_encrypt_returns_ciphertext_different_from_plaintext(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INTEGRATION_CREDENTIALS_KEY", _VALID_KEY)

    ciphertext = crypto.encrypt("my-secret-token")

    assert ciphertext != "my-secret-token"
    assert "my-secret-token" not in ciphertext


def test_decrypt_of_encrypt_round_trips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTEGRATION_CREDENTIALS_KEY", _VALID_KEY)

    plaintext = "another-secret-value"

    assert crypto.decrypt(crypto.encrypt(plaintext)) == plaintext


@pytest.mark.parametrize("missing_value", [None, ""])
def test_missing_key_raises_clear_error_on_encrypt(
    monkeypatch: pytest.MonkeyPatch, missing_value: str | None
) -> None:
    if missing_value is None:
        monkeypatch.delenv("INTEGRATION_CREDENTIALS_KEY", raising=False)
    else:
        monkeypatch.setenv("INTEGRATION_CREDENTIALS_KEY", missing_value)

    with pytest.raises(crypto.MissingCredentialsKeyError):
        crypto.encrypt("plaintext")


@pytest.mark.parametrize("missing_value", [None, ""])
def test_missing_key_raises_clear_error_on_decrypt(
    monkeypatch: pytest.MonkeyPatch, missing_value: str | None
) -> None:
    if missing_value is None:
        monkeypatch.delenv("INTEGRATION_CREDENTIALS_KEY", raising=False)
    else:
        monkeypatch.setenv("INTEGRATION_CREDENTIALS_KEY", missing_value)

    with pytest.raises(crypto.MissingCredentialsKeyError):
        crypto.decrypt("gAAAAA==")
