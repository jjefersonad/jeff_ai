"""Testes de `src/infrastructure/usage/user_key.py` (convenção de user_key)."""
from __future__ import annotations

from src.infrastructure.usage.user_key import (
    UNKNOWN_USER_KEY,
    resolve_user_key,
    telegram_user_key,
    web_user_key,
)


def test_web_user_key_and_telegram_user_key_formats() -> None:
    assert web_user_key("abc") == "web:abc"
    assert telegram_user_key("999") == "telegram:999"


def test_resolve_user_key_fallbacks() -> None:
    owner = "550e8400-e29b-41d4-a716-446655440000"
    assert resolve_user_key(user_key="telegram:999", owner=owner) == "telegram:999"
    assert resolve_user_key(owner=owner) == f"web:{owner}"
    assert resolve_user_key() == UNKNOWN_USER_KEY
    assert UNKNOWN_USER_KEY == "unknown"
