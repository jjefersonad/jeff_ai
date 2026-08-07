"""Testes de consumo de código de vínculo no webhook do WhatsApp
(task `whatsapp-evolution-channel-task-linking-3`).

Cobre os unit-tests linkados à task no OpenSddRag:

- unit-1 (whatsapp-channel REQ-001, cenário "Vínculo bem-sucedido dentro do
  prazo"): texto igual a um código pendente e não expirado cria a entrada
  `user_integrations` (`whatsapp_business`, `config={phone_number}`) associada
  ao `user_id` dono do código, e invalida o código.
- unit-2 (whatsapp-channel REQ-001, cenário "Código expirado ou inexistente"):
  texto que não corresponde a nenhum código pendente não cria vínculo algum
  (segue para o fluxo normal de autorização, `task-channel-3`).

Repositórios são fakes injetados via override de dependency, mesmo padrão de
`test_whatsapp_link_code_endpoint.py`.

`_agent_runner` é override'd por um fake (`_FakeAgentRunner`) pelo mesmo
motivo de `test_whatsapp_webhook_authorization.py`: estes testes cobrem
consumo de código (`task-linking-3`), não o roteamento real (`task-channel-4`).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
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


def _sample_messages_upsert_payload(
    *, text: str, phone_number: str = "5511999998888"
) -> dict[str, object]:
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


_TOKEN = "test-webhook-token-abc123"


@pytest.fixture(autouse=True)
def _evolution_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVOLUTION_API_URL", "http://evolution_api:8080")
    monkeypatch.setenv("EVOLUTION_API_KEY", "fake-key")
    monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "jeff-ai-central")
    monkeypatch.setenv("EVOLUTION_WEBHOOK_TOKEN", _TOKEN)


@pytest.fixture(autouse=True)
def _unauthorized_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Estes testes cobrem só o consumo de código (`task-linking-3`); o filtro
    de autorização (`task-channel-3`, downstream do consumo) não é o que está
    sob teste aqui, então `resolve_whatsapp_user_id` é neutralizado para não
    depender de `POSTGRES_URI` real."""

    async def _fake_resolve(phone_number: str) -> None:
        return None

    monkeypatch.setattr(whatsapp_webhook_router, "resolve_whatsapp_user_id", _fake_resolve)


@pytest.fixture
def link_codes() -> _FakeWhatsAppLinkCodeRepository:
    return _FakeWhatsAppLinkCodeRepository()


@pytest.fixture
def user_integrations() -> _FakeUserIntegrationRepository:
    return _FakeUserIntegrationRepository()


@pytest.fixture
def client(
    link_codes: _FakeWhatsAppLinkCodeRepository,
    user_integrations: _FakeUserIntegrationRepository,
):
    """`require_auth` é override'd aqui só por padronização com os demais
    arquivos de teste — na prática nem entra em jogo, já que
    `/api/webhooks/whatsapp/` está em `PUBLIC_PATHS` (o token na URL é o
    mecanismo de autenticação real, ver `test_whatsapp_webhook_authorization.
    test_webhook_path_is_exempt_from_global_session_auth`)."""
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


async def test_valid_pending_code_creates_binding_and_invalidates_code(
    client: TestClient,
    link_codes: _FakeWhatsAppLinkCodeRepository,
    user_integrations: _FakeUserIntegrationRepository,
) -> None:
    """whatsapp-evolution-channel-task-linking-3-unit-1."""
    await link_codes.save(
        WhatsAppLinkCode(
            code="ABC123",
            user_id="user-a",
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
    )

    payload = _sample_messages_upsert_payload(text="ABC123", phone_number="5511999998888")
    resp = client.post(f"/api/webhooks/whatsapp/{_TOKEN}", json=payload)

    assert resp.status_code == 200, resp.text
    bound = await user_integrations.list_by_user("user-a")
    assert len(bound) == 1
    assert bound[0].integration_type == "whatsapp_business"
    assert bound[0].config == {"phone_number": "5511999998888"}
    assert await link_codes.get("ABC123") is None


async def test_text_not_matching_any_code_does_not_create_binding(
    client: TestClient,
    user_integrations: _FakeUserIntegrationRepository,
) -> None:
    """whatsapp-evolution-channel-task-linking-3-unit-2."""
    payload = _sample_messages_upsert_payload(text="oi, tudo bem?", phone_number="5511999998888")
    resp = client.post(f"/api/webhooks/whatsapp/{_TOKEN}", json=payload)

    assert resp.status_code == 200, resp.text
    assert await user_integrations.list_all() == []
