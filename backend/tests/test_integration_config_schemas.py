"""Testes de `src/application/integrations/config_schemas.py`.

Cobre a task `user-integration-credentials-task-store-1`: registro de schema
Pydantic por `integration_type`, validado na fronteira do caso de uso
(REQ-003 do spec `user-integration-credentials-store`).
"""
from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from src.application.integrations import config_schemas


def test_validate_config_accepts_valid_telegram_payload() -> None:
    result = config_schemas.validate_config("telegram", {"chat_id": "123"})

    assert result.chat_id == "123"


def test_validate_config_rejects_telegram_payload_missing_chat_id() -> None:
    with pytest.raises(ValidationError):
        config_schemas.validate_config("telegram", {})


def test_register_new_integration_type_validates_immediately() -> None:
    class _ThrowawayConfig(BaseModel):
        foo: str

    config_schemas.register_integration_type("test_type", _ThrowawayConfig)

    result = config_schemas.validate_config("test_type", {"foo": "bar"})

    assert result.foo == "bar"
