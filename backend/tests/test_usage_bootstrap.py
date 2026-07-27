"""Bootstrap de `token_usage_events` no lifespan web e no gateway Telegram.

Cobre `track-user-token-usage-task-recording-5-unit-1` (REQ-001):

- WHEN o lifespan do webapp (ou helper de bootstrap testável) executa
- THEN `usage.ensure_schema` é invocado
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import src.infrastructure.telegram.telegram_gateway as telegram_gateway
import src.infrastructure.usage.schema as usage_schema
import src.infrastructure.web.webapp as webapp


def test_webapp_lifespan_calls_usage_ensure_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-1: lifespan do webapp invoca usage.ensure_schema com POSTGRES_URI."""
    calls: list[str] = []
    monkeypatch.setenv("POSTGRES_URI", "postgresql://usage-bootstrap")

    monkeypatch.setattr(
        webapp, "init_auth_schema", lambda conninfo: calls.append(f"auth:{conninfo}")
    )
    monkeypatch.setattr(
        webapp,
        "ensure_ownership_schema",
        lambda conninfo: calls.append(f"ownership:{conninfo}"),
    )
    monkeypatch.setattr(
        webapp,
        "ensure_attachments_schema",
        lambda conninfo: calls.append(f"attachments:{conninfo}"),
    )
    monkeypatch.setattr(
        webapp,
        "ensure_usage_schema",
        lambda conninfo: calls.append(f"usage:{conninfo}"),
    )

    async def _fake_init_pool(conninfo: str) -> None:
        calls.append(f"pool:{conninfo}")

    async def _fake_close_pool() -> None:
        calls.append("close_pool")

    monkeypatch.setattr(webapp, "init_pool", _fake_init_pool)
    monkeypatch.setattr(webapp, "close_pool", _fake_close_pool)

    with TestClient(webapp.app):
        pass

    assert "usage:postgresql://usage-bootstrap" in calls
    # Schema de usage deve existir antes do pool (records podem ocorrer após yield).
    assert calls.index("usage:postgresql://usage-bootstrap") < calls.index(
        "pool:postgresql://usage-bootstrap"
    )


def test_telegram_gateway_main_calls_usage_ensure_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gateway Telegram também garante o schema antes de aceitar messages."""
    usage_calls: list[str] = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_AUTHORIZED_CHAT_ID", "123")
    monkeypatch.setenv("POSTGRES_URI", "postgresql://tg-usage")

    monkeypatch.setattr(
        telegram_gateway,
        "bootstrap_config",
        lambda: telegram_gateway.TelegramConfig(
            bot_token="fake-token",
            authorized_chat_id="123",
        ),
    )
    monkeypatch.setattr(
        "src.infrastructure.telegram.schema.ensure_telegram_threads_schema",
        lambda uri: None,
    )
    monkeypatch.setattr(
        usage_schema,
        "ensure_schema",
        lambda uri: usage_calls.append(uri),
    )
    monkeypatch.setattr(
        telegram_gateway, "build_runner", lambda *, postgres_uri: object()
    )

    class _FakeApp:
        bot = object()

        def add_handler(self, *_a: Any, **_k: Any) -> None:
            return None

        def run_polling(self, *_a: Any, **_k: Any) -> None:
            return None

    monkeypatch.setattr(telegram_gateway, "build_application", lambda _cfg: _FakeApp())

    assert telegram_gateway.main() == 0
    assert usage_calls == ["postgresql://tg-usage"]


def test_unified_run_config_registers_usage_callback_when_postgres_uri_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Decisão web: callback GLOBAL no grafo quando POSTGRES_URI está definido."""
    from src.agents.unified.agent import _unified_run_config
    from src.infrastructure.usage.callback import UsageRecordingCallback

    monkeypatch.setenv("POSTGRES_URI", "postgresql://graph-usage")
    config = _unified_run_config()

    assert config["recursion_limit"] == 1000
    callbacks = config.get("callbacks") or []
    assert any(isinstance(cb, UsageRecordingCallback) for cb in callbacks)


def test_unified_run_config_omits_callback_without_postgres_uri(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sem POSTGRES_URI o grafo sobe sem callback (testes/import local)."""
    from src.agents.unified.agent import _unified_run_config

    monkeypatch.delenv("POSTGRES_URI", raising=False)
    config = _unified_run_config()

    assert config == {"recursion_limit": 1000}
