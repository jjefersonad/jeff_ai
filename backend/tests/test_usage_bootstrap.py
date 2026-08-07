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


def _stub_webapp_schemas_not_under_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Evita conexão real em ensures/deps que o teste não cobre.

    Schemas adicionados depois (MCP, scheduled_tasks, ChannelRegistry) quebram
    o TestClient se não forem stubados — o lifespan chama todos em sequência.
    """
    monkeypatch.setattr(
        "src.composition.dependencies.build_dependencies",
        lambda: None,
    )
    monkeypatch.setattr(webapp, "ensure_user_mcp_servers_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_scheduled_tasks_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_crm_schema", lambda conninfo: None)


def test_webapp_lifespan_calls_usage_ensure_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-1: lifespan do webapp invoca usage.ensure_schema com POSTGRES_URI."""
    calls: list[str] = []
    monkeypatch.setenv("POSTGRES_URI", "postgresql://usage-bootstrap")
    _stub_webapp_schemas_not_under_test(monkeypatch)

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
    # Adicionados por whatsapp-evolution-channel-task-prereq-1/-linking-2 — sem
    # mockar, o lifespan tentaria conectar de verdade em "postgresql://usage-bootstrap".
    monkeypatch.setattr(webapp, "ensure_user_integrations_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_telegram_link_codes_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_whatsapp_link_codes_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_whatsapp_threads_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_user_mcp_servers_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_scheduled_tasks_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_crm_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_langgraph_checkpoint_schema", lambda conninfo: None)

    async def _fake_init_pool(conninfo: str) -> None:
        calls.append(f"pool:{conninfo}")

    async def _fake_close_pool() -> None:
        calls.append("close_pool")

    async def _fake_reschedule_pending_tasks(conninfo: str) -> None:
        return None

    monkeypatch.setattr(webapp, "init_pool", _fake_init_pool)
    monkeypatch.setattr(webapp, "close_pool", _fake_close_pool)
    monkeypatch.setattr(webapp, "_reschedule_pending_tasks", _fake_reschedule_pending_tasks)
    monkeypatch.setattr(webapp.task_scheduler, "start", lambda: None)
    monkeypatch.setattr(webapp.task_scheduler, "shutdown", lambda wait=True: None)

    with TestClient(webapp.app):
        pass

    assert "usage:postgresql://usage-bootstrap" in calls
    # Schema de usage deve existir antes do pool (records podem ocorrer após yield).
    assert calls.index("usage:postgresql://usage-bootstrap") < calls.index(
        "pool:postgresql://usage-bootstrap"
    )


def test_webapp_lifespan_calls_user_integrations_and_telegram_link_codes_ensure_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """whatsapp-evolution-channel-task-prereq-1-unit-1 (2ª parte da acceptance criteria):

    lifespan do webapp também garante os schemas `user_integrations` e
    `telegram_link_codes` — sem isso, `integrations_router` (montado no mesmo
    task) responderia 401/200 normalmente mas quebraria no primeiro INSERT/
    SELECT contra tabelas inexistentes.
    """
    calls: list[str] = []
    monkeypatch.setenv("POSTGRES_URI", "postgresql://prereq-bootstrap")
    _stub_webapp_schemas_not_under_test(monkeypatch)

    monkeypatch.setattr(webapp, "init_auth_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_ownership_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_attachments_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_usage_schema", lambda conninfo: None)
    monkeypatch.setattr(
        webapp,
        "ensure_user_integrations_schema",
        lambda conninfo: calls.append(f"user_integrations:{conninfo}"),
    )
    monkeypatch.setattr(
        webapp,
        "ensure_telegram_link_codes_schema",
        lambda conninfo: calls.append(f"telegram_link_codes:{conninfo}"),
    )
    # whatsapp-evolution-channel-task-linking-2: mockado sem asserção própria
    # aqui (coberta em test_webapp_lifespan_calls_whatsapp_link_codes_ensure_schema
    # abaixo) — só precisa não tentar conectar de verdade.
    monkeypatch.setattr(webapp, "ensure_whatsapp_link_codes_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_whatsapp_threads_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_user_mcp_servers_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_scheduled_tasks_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_crm_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_langgraph_checkpoint_schema", lambda conninfo: None)

    async def _fake_init_pool(conninfo: str) -> None:
        calls.append(f"pool:{conninfo}")

    async def _fake_close_pool() -> None:
        return None

    async def _fake_reschedule_pending_tasks(conninfo: str) -> None:
        return None

    monkeypatch.setattr(webapp, "init_pool", _fake_init_pool)
    monkeypatch.setattr(webapp, "close_pool", _fake_close_pool)
    monkeypatch.setattr(webapp, "_reschedule_pending_tasks", _fake_reschedule_pending_tasks)
    monkeypatch.setattr(webapp.task_scheduler, "start", lambda: None)
    monkeypatch.setattr(webapp.task_scheduler, "shutdown", lambda wait=True: None)

    with TestClient(webapp.app):
        pass

    assert "user_integrations:postgresql://prereq-bootstrap" in calls
    assert "telegram_link_codes:postgresql://prereq-bootstrap" in calls


def test_webapp_lifespan_calls_whatsapp_link_codes_ensure_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """whatsapp-evolution-channel-task-linking-2: lifespan garante `whatsapp_link_codes`.

    Sem isso, `POST /api/integrations/whatsapp/link-code` quebraria no
    primeiro INSERT contra uma tabela inexistente.
    """
    calls: list[str] = []
    monkeypatch.setenv("POSTGRES_URI", "postgresql://linking-2-bootstrap")
    _stub_webapp_schemas_not_under_test(monkeypatch)

    monkeypatch.setattr(webapp, "init_auth_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_ownership_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_attachments_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_usage_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_user_integrations_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_telegram_link_codes_schema", lambda conninfo: None)
    monkeypatch.setattr(
        webapp,
        "ensure_whatsapp_link_codes_schema",
        lambda conninfo: calls.append(f"whatsapp_link_codes:{conninfo}"),
    )
    monkeypatch.setattr(webapp, "ensure_whatsapp_threads_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_user_mcp_servers_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_scheduled_tasks_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_crm_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_langgraph_checkpoint_schema", lambda conninfo: None)

    async def _fake_init_pool(conninfo: str) -> None:
        calls.append(f"pool:{conninfo}")

    async def _fake_close_pool() -> None:
        return None

    async def _fake_reschedule_pending_tasks(conninfo: str) -> None:
        return None

    monkeypatch.setattr(webapp, "init_pool", _fake_init_pool)
    monkeypatch.setattr(webapp, "close_pool", _fake_close_pool)
    monkeypatch.setattr(webapp, "_reschedule_pending_tasks", _fake_reschedule_pending_tasks)
    monkeypatch.setattr(webapp.task_scheduler, "start", lambda: None)
    monkeypatch.setattr(webapp.task_scheduler, "shutdown", lambda wait=True: None)

    with TestClient(webapp.app):
        pass

    assert "whatsapp_link_codes:postgresql://linking-2-bootstrap" in calls
    assert calls.index("whatsapp_link_codes:postgresql://linking-2-bootstrap") < calls.index(
        "pool:postgresql://linking-2-bootstrap"
    )


def test_webapp_lifespan_calls_whatsapp_threads_ensure_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`ensure_whatsapp_threads_schema` existia mas nunca era chamada pelo lifespan:
    `get_or_create_thread_id` quebrava com `UndefinedTable` na primeira mensagem
    recebida após o vínculo do número (tabela `whatsapp_threads` nunca criada).
    """
    calls: list[str] = []
    monkeypatch.setenv("POSTGRES_URI", "postgresql://threads-bootstrap")
    _stub_webapp_schemas_not_under_test(monkeypatch)

    monkeypatch.setattr(webapp, "init_auth_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_ownership_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_attachments_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_usage_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_user_integrations_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_telegram_link_codes_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_whatsapp_link_codes_schema", lambda conninfo: None)
    monkeypatch.setattr(
        webapp,
        "ensure_whatsapp_threads_schema",
        lambda conninfo: calls.append(f"whatsapp_threads:{conninfo}"),
    )
    monkeypatch.setattr(webapp, "ensure_user_mcp_servers_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_scheduled_tasks_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_crm_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_langgraph_checkpoint_schema", lambda conninfo: None)

    async def _fake_init_pool(conninfo: str) -> None:
        calls.append(f"pool:{conninfo}")

    async def _fake_close_pool() -> None:
        return None

    async def _fake_reschedule_pending_tasks(conninfo: str) -> None:
        return None

    monkeypatch.setattr(webapp, "init_pool", _fake_init_pool)
    monkeypatch.setattr(webapp, "close_pool", _fake_close_pool)
    monkeypatch.setattr(webapp, "_reschedule_pending_tasks", _fake_reschedule_pending_tasks)
    monkeypatch.setattr(webapp.task_scheduler, "start", lambda: None)
    monkeypatch.setattr(webapp.task_scheduler, "shutdown", lambda wait=True: None)

    with TestClient(webapp.app):
        pass

    assert "whatsapp_threads:postgresql://threads-bootstrap" in calls
    assert calls.index("whatsapp_threads:postgresql://threads-bootstrap") < calls.index(
        "pool:postgresql://threads-bootstrap"
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
        "src.infrastructure.agent_runtime.checkpoint_schema.ensure_langgraph_checkpoint_schema",
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
