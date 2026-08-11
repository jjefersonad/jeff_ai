"""Bootstrap de `ensure_email_schema` no lifespan do webapp."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import src.infrastructure.web.webapp as webapp


def _patch_lifespan_deps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.composition.dependencies.build_dependencies", lambda: None
    )
    monkeypatch.setattr(webapp, "init_auth_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_ownership_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_attachments_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_usage_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_user_integrations_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_user_mcp_servers_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_telegram_link_codes_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_whatsapp_link_codes_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_whatsapp_threads_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_scheduled_tasks_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_crm_schema", lambda conninfo: None)
    monkeypatch.setattr(webapp, "ensure_langgraph_checkpoint_schema", lambda conninfo: None)

    async def _fake_init_pool(conninfo: str) -> None:
        return None

    async def _fake_close_pool() -> None:
        return None

    async def _fake_reschedule(conninfo: str) -> None:
        return None

    monkeypatch.setattr(webapp, "init_pool", _fake_init_pool)
    monkeypatch.setattr(webapp, "close_pool", _fake_close_pool)
    monkeypatch.setattr(webapp, "_reschedule_pending_tasks", _fake_reschedule)
    monkeypatch.setattr(webapp.task_scheduler, "start", lambda: None)
    monkeypatch.setattr(webapp.task_scheduler, "shutdown", lambda wait=True: None)


def test_webapp_lifespan_calls_email_schema_ensure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN lifespan startup runs THEN ensure_email_schema is called with POSTGRES_URI."""
    calls: list[str] = []
    monkeypatch.setenv("POSTGRES_URI", "postgresql://email-webapp")
    _patch_lifespan_deps(monkeypatch)

    monkeypatch.setattr(
        webapp,
        "ensure_email_schema",
        lambda conninfo: calls.append(conninfo),
    )

    with TestClient(webapp.app):
        pass

    assert calls == ["postgresql://email-webapp"]
