"""Testes do tratamento de falha do webhook WhatsApp (REQ-006, task `channel-5`).

Cobre o unit-test linkado à task no OpenSddRag:

- unit-1 (whatsapp-channel REQ-006, cenário "Timeout ou exceção na invocação
  do agente"): quando `AgentRunnerPort.run()` levanta exceção OU o
  `AgentRunResult.status` retornado indica falha/timeout, o sistema envia uma
  mensagem de erro ao `phone_number` de origem via `evolution_client.send_text`,
  sem propagar a exceção para o processo que atende o webhook.

Mesmo padrão de dependency override dos demais testes deste router
(`test_whatsapp_webhook_authorization.py`).
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import src.infrastructure.web.webapp as webapp
import src.infrastructure.web.whatsapp_webhook_router as whatsapp_webhook_router
from src.application.ports.agent_runner import AgentRunResult
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.application.ports.whatsapp_link_code_repository import (
    WhatsAppLinkCodeRepositoryPort,
)
from src.domain.integrations import UserIntegration, WhatsAppLinkCode
from src.infrastructure.auth.dependencies import require_auth


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
        return AgentRunResult(thread_id=kwargs["thread_id"], status="timeout", error="timed out")


def _sample_messages_upsert_payload(*, text: str, phone_number: str) -> dict[str, object]:
    """Payload representativo de um webhook `messages.upsert` da Evolution API."""
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


@pytest.fixture(autouse=True)
def _evolution_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVOLUTION_API_URL", "http://evolution_api:8080")
    monkeypatch.setenv("EVOLUTION_API_KEY", "fake-key")
    monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "jeff-ai-central")


@pytest.fixture(autouse=True)
def _linked_phone_number(monkeypatch: pytest.MonkeyPatch) -> None:
    """`phone_number="5511111111111"` sempre resolve para um `user_id` vinculado
    e um `thread_id` fixo — estes testes cobrem só o tratamento de falha
    downstream da autorização (`task-channel-3`), já coberta em outro arquivo."""

    async def _fake_resolve(phone_number: str) -> str | None:
        return "user-a"

    def _fake_get_or_create_thread_id(phone_number: str) -> str:
        return "thread-xyz"

    monkeypatch.setattr(whatsapp_webhook_router, "resolve_whatsapp_user_id", _fake_resolve)
    monkeypatch.setattr(
        whatsapp_webhook_router, "get_or_create_thread_id", _fake_get_or_create_thread_id
    )


@pytest.fixture
def send_text_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    """Espiona `evolution_client.send_text` sem bater na rede."""
    calls: list[tuple[str, str, str]] = []

    async def _fake_send_text(instance: str, phone_number: str, text: str) -> None:
        calls.append((instance, phone_number, text))

    monkeypatch.setattr(whatsapp_webhook_router, "send_text", _fake_send_text)
    return calls


def _client(agent_runner: Any) -> TestClient:
    link_codes = _FakeWhatsAppLinkCodeRepository()
    user_integrations = _FakeUserIntegrationRepository()
    webapp.app.dependency_overrides[require_auth] = lambda: None
    webapp.app.dependency_overrides[
        whatsapp_webhook_router._whatsapp_link_code_repository
    ] = lambda: link_codes
    webapp.app.dependency_overrides[
        whatsapp_webhook_router._user_integration_repository
    ] = lambda: user_integrations
    webapp.app.dependency_overrides[whatsapp_webhook_router._agent_runner] = lambda: agent_runner
    return TestClient(webapp.app)


@pytest.fixture
def _cleanup_overrides():
    yield
    webapp.app.dependency_overrides.pop(require_auth, None)
    webapp.app.dependency_overrides.pop(whatsapp_webhook_router._whatsapp_link_code_repository, None)
    webapp.app.dependency_overrides.pop(whatsapp_webhook_router._user_integration_repository, None)
    webapp.app.dependency_overrides.pop(whatsapp_webhook_router._agent_runner, None)


async def test_agent_runner_exception_notifies_phone_number_without_propagating(
    send_text_calls: list[tuple[str, str, str]], _cleanup_overrides: None
) -> None:
    """whatsapp-evolution-channel-task-channel-5-unit-1 (exceção)."""
    client = _client(_RaisingAgentRunner())
    payload = _sample_messages_upsert_payload(text="oi, tudo bem?", phone_number="5511111111111")

    resp = client.post("/api/webhooks/whatsapp", json=payload)

    assert resp.status_code == 200, resp.text
    assert len(send_text_calls) == 1
    instance, phone_number, _text = send_text_calls[0]
    assert instance == "jeff-ai-central"
    assert phone_number == "5511111111111"


async def test_agent_runner_failure_status_notifies_phone_number(
    send_text_calls: list[tuple[str, str, str]], _cleanup_overrides: None
) -> None:
    """whatsapp-evolution-channel-task-channel-5-unit-1 (status de falha/timeout)."""
    client = _client(_FailingStatusAgentRunner())
    payload = _sample_messages_upsert_payload(text="oi, tudo bem?", phone_number="5511111111111")

    resp = client.post("/api/webhooks/whatsapp", json=payload)

    assert resp.status_code == 200, resp.text
    assert len(send_text_calls) == 1
    assert send_text_calls[0][1] == "5511111111111"
