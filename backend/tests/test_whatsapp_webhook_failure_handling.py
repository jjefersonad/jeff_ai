"""Testes do tratamento de falha do webhook WhatsApp (REQ-006 legado /
`HandleChatMessage` + `WhatsAppChannel` após whatsapp-1).

Quando `AgentRunnerPort.run()` levanta exceção OU o `AgentRunResult.status`
indica falha, o canal envia mensagem de erro ao `phone_number` via
`WhatsAppChannel.deliver(kind="failure")` → `evolution_client.send_text`,
sem propagar a exceção.

Chama o endpoint diretamente (não via `TestClient`) — mesmo motivo de
`test_whatsapp_webhook_slash_commands.py` (FastAPI 204 no scheduling_router
bloqueia a coleção de testes que sobem `webapp.app`).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import src.infrastructure.web.whatsapp_webhook_router as whatsapp_webhook_router
from src.application.ports.agent_runner import AgentRunResult
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.application.ports.whatsapp_link_code_repository import (
    WhatsAppLinkCodeRepositoryPort,
)
from src.domain.integrations import UserIntegration, WhatsAppLinkCode


class _FakeWhatsAppLinkCodeRepository(WhatsAppLinkCodeRepositoryPort):
    def __init__(self) -> None:
        self._by_code: dict[str, WhatsAppLinkCode] = {}

    async def save(self, link_code: WhatsAppLinkCode) -> None:
        self._by_code[link_code.code] = link_code

    async def get(self, code: str) -> WhatsAppLinkCode | None:
        return self._by_code.get(code)

    async def delete(self, code: str) -> None:
        self._by_code.pop(code, None)


class _FakeUserIntegrationRepository(UserIntegrationRepositoryPort):
    def __init__(self) -> None:
        self._store: dict[str, UserIntegration] = {}

    async def save(self, integration: UserIntegration) -> None:
        self._store[integration.id] = integration

    async def get(self, integration_id: str) -> UserIntegration | None:
        return self._store.get(integration_id)

    async def list_by_user(self, user_id: str) -> list[UserIntegration]:
        return [i for i in self._store.values() if i.user_id == user_id]

    async def list_all(self) -> list[UserIntegration]:
        return list(self._store.values())

    async def delete(self, integration_id: str) -> None:
        self._store.pop(integration_id, None)


class _RaisingAgentRunner:
    async def run(self, **kwargs: Any) -> AgentRunResult:
        raise RuntimeError("boom")


class _FailingStatusAgentRunner:
    async def run(self, **kwargs: Any) -> AgentRunResult:
        return AgentRunResult(
            thread_id=kwargs["thread_id"], status="timeout", error="timed out"
        )


class _FakeRequest:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    async def json(self) -> dict[str, object]:
        return self._payload


def _sample_messages_upsert_payload(*, text: str, phone_number: str) -> dict[str, object]:
    return {
        "event": "messages.upsert",
        "instance": "jeff-ai-central",
        "data": {
            "key": {
                "remoteJid": f"{phone_number}@s.whatsapp.net",
                "fromMe": False,
                "id": "3EB0ABCDEF1234567890",
            },
            "message": {"conversation": text},
            "messageType": "conversation",
        },
    }


_TOKEN = "test-webhook-token-abc123"
_PHONE = "5511111111111"


@pytest.fixture(autouse=True)
def _evolution_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVOLUTION_API_URL", "http://evolution_api:8080")
    monkeypatch.setenv("EVOLUTION_API_KEY", "fake-key")
    monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "jeff-ai-central")
    monkeypatch.setenv("EVOLUTION_WEBHOOK_TOKEN", _TOKEN)


@pytest.fixture(autouse=True)
def _linked_phone_number(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_resolve(phone_number: str) -> str | None:
        return "user-a"

    def _fake_get_or_create_thread_id(phone_number: str) -> str:
        return "thread-xyz"

    monkeypatch.setattr(whatsapp_webhook_router, "resolve_whatsapp_user_id", _fake_resolve)
    monkeypatch.setattr(
        whatsapp_webhook_router, "get_or_create_thread_id", _fake_get_or_create_thread_id
    )
    dispatch = AsyncMock(return_value=False)
    fake_commands = MagicMock()
    fake_commands.dispatch_command = dispatch
    monkeypatch.setattr(whatsapp_webhook_router, "commands", fake_commands)


@pytest.fixture
def send_text_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    calls: list[tuple[str, str, str]] = []

    async def _fake_send_text(instance: str, phone_number: str, text: str) -> None:
        calls.append((instance, phone_number, text))

    monkeypatch.setattr(
        "src.infrastructure.channels.whatsapp_channel.evolution_client.send_text",
        _fake_send_text,
    )
    return calls


@pytest.mark.asyncio
async def test_agent_runner_exception_notifies_phone_number_without_propagating(
    send_text_calls: list[tuple[str, str, str]],
) -> None:
    """Exceção no runner → `kind=failure` via WhatsAppChannel."""
    result = await whatsapp_webhook_router.whatsapp_webhook_endpoint(
        token=_TOKEN,
        request=_FakeRequest(
            _sample_messages_upsert_payload(text="oi, tudo bem?", phone_number=_PHONE)
        ),
        link_codes=_FakeWhatsAppLinkCodeRepository(),
        user_integrations=_FakeUserIntegrationRepository(),
        agent_runner=_RaisingAgentRunner(),
    )

    assert result == {"received": True}
    assert len(send_text_calls) == 1
    instance, phone_number, text = send_text_calls[0]
    assert instance == "jeff-ai-central"
    assert phone_number == _PHONE
    assert text
    assert "falha" in text.lower()


@pytest.mark.asyncio
async def test_agent_runner_failure_status_notifies_phone_number(
    send_text_calls: list[tuple[str, str, str]],
) -> None:
    """status=timeout → `kind=failure` via WhatsAppChannel."""
    result = await whatsapp_webhook_router.whatsapp_webhook_endpoint(
        token=_TOKEN,
        request=_FakeRequest(
            _sample_messages_upsert_payload(text="oi, tudo bem?", phone_number=_PHONE)
        ),
        link_codes=_FakeWhatsAppLinkCodeRepository(),
        user_integrations=_FakeUserIntegrationRepository(),
        agent_runner=_FailingStatusAgentRunner(),
    )

    assert result == {"received": True}
    assert len(send_text_calls) == 1
    assert send_text_calls[0][1] == _PHONE
