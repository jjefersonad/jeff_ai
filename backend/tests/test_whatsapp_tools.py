"""Testes de `src/tools/whatsapp_tools.py`.

Cobre a task `whatsapp-evolution-channel-task-tools-2`:

- Unit 2: sem `phone_number` explícito, numa sessão com vínculo WhatsApp
  ativo, a tool envia ao `phone_number` vinculado ao `user_id` resolvido.
- Unit 3: sem `phone_number` explícito e sem vínculo WhatsApp, a tool
  retorna erro sem chamar a Evolution API.

Cobre a task `whatsapp-evolution-channel-task-tools-3`:

- Unit 1: falha por janela de 24h expirada (`error.code=131047`, relayed
  pela Evolution API em modo Cloud API) retorna `error_kind="outside_window"`,
  `retryable=False`, sem levantar.
- Unit 2: falha de rate limit (HTTP 429) retorna `error_kind="rate_limited"`,
  `retryable=True`, sem levantar.
"""
from __future__ import annotations

from typing import Any

import httpx
import pytest

from src.domain.integrations import UserIntegration
from src.tools import whatsapp_tools


def _whatsapp_integration(*, user_id: str, phone_number: str) -> UserIntegration:
    return UserIntegration(
        id="integration-1",
        user_id=user_id,
        integration_type="whatsapp_business",
        config={"phone_number": phone_number},
    )


def _patch_resolve_user_id(monkeypatch: pytest.MonkeyPatch, user_id: str | None) -> None:
    async def _fake_resolve_user_id() -> str | None:
        return user_id

    monkeypatch.setattr(whatsapp_tools, "resolve_user_id", _fake_resolve_user_id)


def _patch_integration_repository(
    monkeypatch: pytest.MonkeyPatch, integrations: list[UserIntegration]
) -> None:
    class _FakeRepository:
        def __init__(self, conninfo: str) -> None:
            self.conninfo = conninfo

        async def list_by_user(self, user_id: str) -> list[UserIntegration]:
            return [i for i in integrations if i.user_id == user_id]

    monkeypatch.setattr(whatsapp_tools, "PostgresUserIntegrationRepository", _FakeRepository)
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")


def _patch_evolution_client(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    """Substitui `evolution_client.send_text`/`bootstrap_config` — sem rede real."""
    sent: list[tuple[str, str, str]] = []

    async def _fake_send_text(instance: str, phone_number: str, text: str) -> None:
        sent.append((instance, phone_number, text))

    _patch_bootstrap_config(monkeypatch)
    monkeypatch.setattr(whatsapp_tools.evolution_client, "send_text", _fake_send_text)
    return sent


def _patch_bootstrap_config(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_bootstrap_config() -> Any:
        return whatsapp_tools.evolution_client.EvolutionConfig(
            api_url="http://evolution_api:8080",
            api_key="fake-key",
            instance_name="jeff-ai-central",
        )

    monkeypatch.setattr(
        whatsapp_tools.evolution_client, "bootstrap_config", _fake_bootstrap_config
    )


def _patch_evolution_client_raising(
    monkeypatch: pytest.MonkeyPatch, exc: httpx.HTTPStatusError
) -> None:
    """Substitui `evolution_client.send_text` para levantar `exc` — sem rede real."""

    async def _fake_send_text(instance: str, phone_number: str, text: str) -> None:
        raise exc

    _patch_bootstrap_config(monkeypatch)
    monkeypatch.setattr(whatsapp_tools.evolution_client, "send_text", _fake_send_text)


def _http_status_error(status_code: int, json_body: dict[str, Any]) -> httpx.HTTPStatusError:
    request = httpx.Request(
        "POST", "http://evolution_api:8080/message/sendText/jeff-ai-central"
    )
    response = httpx.Response(status_code, json=json_body, request=request)
    return httpx.HTTPStatusError("erro na Evolution API", request=request, response=response)


async def test_send_whatsapp_message_without_destination_uses_linked_phone_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """whatsapp-evolution-channel-task-tools-2-unit-2."""
    _patch_resolve_user_id(monkeypatch, "user-xyz")
    _patch_integration_repository(
        monkeypatch, [_whatsapp_integration(user_id="user-xyz", phone_number="5511999990000")]
    )
    sent = _patch_evolution_client(monkeypatch)

    result = await whatsapp_tools.send_whatsapp_message.ainvoke({"text": "oi"})

    assert result["success"] is True
    assert sent == [("jeff-ai-central", "5511999990000", "oi")]


async def test_send_whatsapp_message_without_link_returns_error_without_calling_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """whatsapp-evolution-channel-task-tools-2-unit-3."""
    _patch_resolve_user_id(monkeypatch, "user-xyz")
    _patch_integration_repository(monkeypatch, [])
    sent = _patch_evolution_client(monkeypatch)

    result = await whatsapp_tools.send_whatsapp_message.ainvoke({"text": "oi"})

    assert result["success"] is False
    assert sent == []


async def test_send_whatsapp_message_without_session_user_returns_error_without_calling_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sessão sem `user_id` resolvível (ex.: sem `user_key`) segue o mesmo
    caminho de erro do vínculo ausente — nunca chama a Evolution API."""
    _patch_resolve_user_id(monkeypatch, None)
    sent = _patch_evolution_client(monkeypatch)

    result = await whatsapp_tools.send_whatsapp_message.ainvoke({"text": "oi"})

    assert result["success"] is False
    assert sent == []


async def test_send_whatsapp_message_with_explicit_destination_ignores_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`phone_number` explícito é usado como está, sem consultar `user_integrations`."""

    def _explode(conninfo: str) -> None:
        raise AssertionError("destino explícito não deveria consultar user_integrations")

    monkeypatch.setattr(whatsapp_tools, "PostgresUserIntegrationRepository", _explode)
    sent = _patch_evolution_client(monkeypatch)

    result = await whatsapp_tools.send_whatsapp_message.ainvoke(
        {"text": "oi", "phone_number": "5511888880000"}
    )

    assert result["success"] is True
    assert sent == [("jeff-ai-central", "5511888880000", "oi")]


async def test_send_whatsapp_message_outside_24h_window_returns_structured_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """whatsapp-evolution-channel-task-tools-3-unit-1."""
    exc = _http_status_error(400, {"error": {"code": 131047, "message": "re-engagement"}})
    _patch_evolution_client_raising(monkeypatch, exc)

    result = await whatsapp_tools.send_whatsapp_message.ainvoke(
        {"text": "oi", "phone_number": "5511888880000"}
    )

    assert result["success"] is False
    assert result["error_kind"] == "outside_window"
    assert result["retryable"] is False


async def test_send_whatsapp_message_rate_limited_returns_structured_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """whatsapp-evolution-channel-task-tools-3-unit-2."""
    exc = _http_status_error(429, {"error": {"code": 130429, "message": "rate limit hit"}})
    _patch_evolution_client_raising(monkeypatch, exc)

    result = await whatsapp_tools.send_whatsapp_message.ainvoke(
        {"text": "oi", "phone_number": "5511888880000"}
    )

    assert result["success"] is False
    assert result["error_kind"] == "rate_limited"
    assert result["retryable"] is True
