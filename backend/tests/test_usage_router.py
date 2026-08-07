"""Testes de `GET /api/usage` (token-usage-reporting, task-reporting-1).

Cobre agregação admin (REQ-001/004), filtros (REQ-002/003) e 403 para
não-admin (REQ-006). Persistência é mockada — coberta em
`test_usage_repository.py`.
"""
from __future__ import annotations

from datetime import UTC, datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

import src.infrastructure.web.usage_router as usage_router
import src.infrastructure.web.webapp as webapp
from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.users import User

_ADMIN = User(id="admin-1", username="alice", password_hash="h", role="admin", is_active=True)
_REGULAR = User(id="user-2", username="bob", password_hash="h", role="user", is_active=True)


@pytest.fixture
def client():
    """Cliente do webapp com auth sobrescrita pelo teste."""
    try:
        yield TestClient(webapp.app)
    finally:
        webapp.app.dependency_overrides.pop(require_auth, None)


def _as_admin() -> None:
    webapp.app.dependency_overrides[require_auth] = lambda: _ADMIN


def _as_user() -> None:
    webapp.app.dependency_overrides[require_auth] = lambda: _REGULAR


def test_get_usage_admin_returns_aggregated_totals(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Unit-1 / REQ-001: admin obtém totais corretos e filters ecoados."""
    _as_admin()
    calls: list[dict[str, Any]] = []

    def _fake_aggregate(self: object, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {
            "user_key": kwargs["user_key"],
            "prompt_tokens": 120,
            "completion_tokens": 80,
            "total_tokens": 200,
            "filters": {"user_key": kwargs["user_key"]},
        }

    monkeypatch.setattr(usage_router.UsageRepository, "aggregate", _fake_aggregate)
    monkeypatch.setenv("POSTGRES_URI", "postgresql://usage-router-test")

    resp = client.get("/api/usage", params={"user_key": "web:alice"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user_key"] == "web:alice"
    assert body["prompt_tokens"] == 120
    assert body["completion_tokens"] == 80
    assert body["total_tokens"] == 200
    assert body["filters"]["user_key"] == "web:alice"
    assert len(calls) == 1
    assert calls[0]["user_key"] == "web:alice"


def test_get_usage_admin_passes_period_and_model_filters(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Unit-2 / REQ-002/003: from/to/model chegam ao aggregate."""
    _as_admin()
    calls: list[dict[str, Any]] = []

    def _fake_aggregate(self: object, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "filters": {
                "from": kwargs["from_ts"],
                "to": kwargs["to_ts"],
                "model": kwargs["model"],
            },
        }

    monkeypatch.setattr(usage_router.UsageRepository, "aggregate", _fake_aggregate)
    monkeypatch.setenv("POSTGRES_URI", "postgresql://usage-router-test")

    resp = client.get(
        "/api/usage",
        params={
            "from": "2026-07-01T00:00:00+00:00",
            "to": "2026-07-25T23:59:59+00:00",
            "model": "minimax-m2.7:cloud",
        },
    )

    assert resp.status_code == 200, resp.text
    assert len(calls) == 1
    assert calls[0]["model"] == "minimax-m2.7:cloud"
    assert calls[0]["from_ts"] == datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC)
    assert calls[0]["to_ts"] == datetime(2026, 7, 25, 23, 59, 59, tzinfo=UTC)
    body = resp.json()
    assert body["total_tokens"] == 15
    assert "filters" in body


def test_get_usage_non_admin_returns_403_without_totals(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Unit-2 / REQ-006: não-admin → 403 e nenhum total revelado."""
    _as_user()
    called = {"aggregate": False}

    def _fake_aggregate(self: object, **kwargs: Any) -> dict[str, Any]:
        called["aggregate"] = True
        return {
            "prompt_tokens": 999,
            "completion_tokens": 999,
            "total_tokens": 1998,
            "filters": {},
        }

    monkeypatch.setattr(usage_router.UsageRepository, "aggregate", _fake_aggregate)
    monkeypatch.setenv("POSTGRES_URI", "postgresql://usage-router-test")

    resp = client.get("/api/usage", params={"user_key": "web:alice"})

    assert resp.status_code == 403
    body = resp.json()
    assert body == {"detail": "Forbidden"}
    assert "prompt_tokens" not in body
    assert "total_tokens" not in body
    assert called["aggregate"] is False
