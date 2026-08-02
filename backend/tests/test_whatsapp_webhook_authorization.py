"""Testes do filtro de autorização do webhook WhatsApp (REQ-003, task `channel-3`).

Cobre os unit-tests linkados à task no OpenSddRag:

- unit-1 (whatsapp-channel REQ-003, cenário "Mensagem de número vinculado"):
  telefone com vínculo ativo (`resolve_whatsapp_user_id` resolve um `user_id`)
  segue processando — obtém/cria o mapeamento `phone_number -> thread_id`
  (proxy observável de "processa normalmente" nesta task; o roteamento real
  para o grafo `unified` é construído por `task-channel-4`).
- unit-2 (whatsapp-channel REQ-003, cenário "Mensagem de número não vinculado"):
  telefone sem vínculo é ignorado — nenhum mapeamento `phone_number -> thread_id`
  é criado.

`resolve_whatsapp_user_id`/`get_or_create_thread_id` são monkeypatched
diretamente no módulo do router (mesmo padrão de `test_ownership_store.py`
para código que constrói seu próprio repositório a partir de `POSTGRES_URI`
em vez de receber via `Depends`).

`_agent_runner` é override'd por um fake (`_FakeAgentRunner`) — o roteamento
real para o grafo `unified` (`task-channel-4`) tem cobertura própria em
`test_whatsapp_authorization.py`; aqui só garantimos que a requisição não
tenta abrir uma conexão Postgres real.
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


class _FakeAgentRunner:
    async def run(self, **kwargs: Any) -> AgentRunResult:
        return AgentRunResult(thread_id=kwargs["thread_id"], status="ok")


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


@pytest.fixture
def client():
    """`link_codes`/`user_integrations` ficam vazios: o texto de teste nunca bate
    com um código pendente, então `RedeemWhatsAppLinkCode` sempre levanta
    `WhatsAppLinkCodeInvalidError` e o fluxo cai direto no filtro de autorização
    (`task-channel-3`), que é o que estes testes exercitam."""
    link_codes = _FakeWhatsAppLinkCodeRepository()
    user_integrations = _FakeUserIntegrationRepository()
    webapp.app.dependency_overrides[require_auth] = lambda: None
    webapp.app.dependency_overrides[
        whatsapp_webhook_router._whatsapp_link_code_repository
    ] = lambda: link_codes
    webapp.app.dependency_overrides[
        whatsapp_webhook_router._user_integration_repository
    ] = lambda: user_integrations
    webapp.app.dependency_overrides[
        whatsapp_webhook_router._agent_runner
    ] = lambda: _FakeAgentRunner()
    try:
        yield TestClient(webapp.app)
    finally:
        webapp.app.dependency_overrides.pop(require_auth, None)
        webapp.app.dependency_overrides.pop(
            whatsapp_webhook_router._whatsapp_link_code_repository, None
        )
        webapp.app.dependency_overrides.pop(
            whatsapp_webhook_router._user_integration_repository, None
        )
        webapp.app.dependency_overrides.pop(whatsapp_webhook_router._agent_runner, None)


@pytest.fixture
def resolution_calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """Espiona `resolve_whatsapp_user_id`/`get_or_create_thread_id` do router.

    `phone_number="5511111111111"` está "vinculado" (resolve para `user-a`);
    qualquer outro número não tem vínculo (resolve para `None`).
    """
    calls: dict[str, list[str]] = {"resolve": [], "thread": []}

    async def _fake_resolve(phone_number: str) -> str | None:
        calls["resolve"].append(phone_number)
        return "user-a" if phone_number == "5511111111111" else None

    def _fake_get_or_create_thread_id(phone_number: str) -> str:
        calls["thread"].append(phone_number)
        return "thread-xyz"

    monkeypatch.setattr(whatsapp_webhook_router, "resolve_whatsapp_user_id", _fake_resolve)
    monkeypatch.setattr(
        whatsapp_webhook_router, "get_or_create_thread_id", _fake_get_or_create_thread_id
    )
    return calls


async def test_linked_phone_number_proceeds_past_authorization_gate(
    client: TestClient, resolution_calls: dict[str, list[str]]
) -> None:
    """whatsapp-evolution-channel-task-channel-3-unit-1."""
    payload = _sample_messages_upsert_payload(text="oi, tudo bem?", phone_number="5511111111111")

    resp = client.post("/api/webhooks/whatsapp", json=payload)

    assert resp.status_code == 200, resp.text
    assert resolution_calls["resolve"] == ["5511111111111"]
    assert resolution_calls["thread"] == ["5511111111111"]


async def test_unlinked_phone_number_is_ignored_without_persisting_mapping(
    client: TestClient, resolution_calls: dict[str, list[str]]
) -> None:
    """whatsapp-evolution-channel-task-channel-3-unit-2."""
    payload = _sample_messages_upsert_payload(text="oi, tudo bem?", phone_number="5522222222222")

    resp = client.post("/api/webhooks/whatsapp", json=payload)

    assert resp.status_code == 200, resp.text
    assert resolution_calls["resolve"] == ["5522222222222"]
    assert resolution_calls["thread"] == []
