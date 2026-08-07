"""Testes do split slash-command vs. mensagem normal no webhook WhatsApp.

Cobre a task `whatsapp-slash-commands-task-channel-1` (3 unidades):

- Unit-1 (whatsapp-channel REQ-004 cenário "Roteamento de uma mensagem
  autorizada"): mensagem autorizada cujo `text` NÃO é slash command cai no
  caminho normal — `commands.dispatch_command` é chamado (retorna `False`),
  `AgentRunnerPort.run()` é chamado.
- Unit-2 (whatsapp-channel REQ-004 cenário "Mensagem reconhecida como slash
  command não é roteada ao agente"): mensagem autorizada cujo `text` é
  `/sessions` (slash command reconhecido) — `commands.dispatch_command` é
  chamado e retorna `True`; `AgentRunnerPort.run()` NÃO é chamado.
- Unit-3 (whatsapp-slash-commands REQ-006 cenário "Slash command de número
  não vinculado"): `phone_number` sem vínculo ativo → `resolve_whatsapp_user_id`
  devolve `None` antes de `commands.dispatch_command` ser chamado; nem o
  dispatcher nem `agent_runner.run` rodam.

Por que chamar o endpoint diretamente (não via `TestClient`):
`whatsapp_webhook_endpoint` é uma função `async def` que recebe um `Request`
do Starlette + três `Depends` para os repositórios; os testes do projeto
que usam `TestClient` (`test_whatsapp_webhook_authorization.py`, `..._failure_handling.py`)
importam `webapp.app` para subir o grafo de rotas. Esse grafo importa o
`scheduling_router` que tem um `status_code=204` incompatível com a versão
atual de FastAPI do projeto (pré-existente, fora do escopo desta task) —
bloquearia a coleção de testes sem dar nenhuma garantia extra de cobertura.
Chamar o endpoint diretamente testa exatamente o que importa para esta task
(o split slash-command vs. mensagem normal) sem acoplar ao estado de outros
routers. `Depends(...)` é uma anotação do FastAPI; quando o caller passa os
valores explicitamente como kwargs, ela é ignorada — mesmo padrão de
quaisquer testes unitários em código que depende de FastAPI.
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


# ============================================================================
# Fakes — paralelos aos de `test_whatsapp_webhook_authorization.py`, mas
# reutilizáveis diretamente (sem `TestClient`).
# ============================================================================


class _RecordingAgentRunner:
    """`AgentRunnerPort` fake — registra cada chamada a `run` em `self.calls`."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def run(self, **kwargs: Any) -> AgentRunResult:
        self.calls.append(kwargs)
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


class _FakeRequest:
    """Stub mínimo de `starlette.requests.Request` — expõe `.json()` async.

    O endpoint faz uma única chamada: `payload = await request.json()`. O
    `_FakeRequest` reproduz isso sem precisar de um `Request` real do
    Starlette (que exigiria um ciclo ASGI completo só para buscar o body).
    """

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
_LINKED_PHONE = "5511111111111"
_UNLINKED_PHONE = "5522222222222"


@pytest.fixture(autouse=True)
def _evolution_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVOLUTION_API_URL", "http://evolution_api:8080")
    monkeypatch.setenv("EVOLUTION_API_KEY", "fake-key")
    monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "jeff-ai-central")
    monkeypatch.setenv("EVOLUTION_WEBHOOK_TOKEN", _TOKEN)


@pytest.fixture
def link_code_repo() -> _FakeWhatsAppLinkCodeRepository:
    return _FakeWhatsAppLinkCodeRepository()


@pytest.fixture
def user_integration_repo() -> _FakeUserIntegrationRepository:
    return _FakeUserIntegrationRepository()


@pytest.fixture
def agent_runner_recorder() -> _RecordingAgentRunner:
    return _RecordingAgentRunner()


@pytest.fixture
def dispatch_command_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Espia `commands.dispatch_command` no módulo do router.

    Substitui o atributo `commands` do router por um `MagicMock` cujo único
    atributo usado no caminho deste teste é `dispatch_command` (espelha o
    padrão `monkeypatch.setattr(commands, "create_thread_for_number", ...)`
    usado em `test_whatsapp_commands.py`).
    """
    mock = AsyncMock()
    fake_commands = MagicMock()
    fake_commands.dispatch_command = mock
    monkeypatch.setattr(whatsapp_webhook_router, "commands", fake_commands)
    return mock


@pytest.fixture
def resolution_calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """Espelha o fixture do `test_whatsapp_webhook_authorization.py`.

    `phone_number = 5511111111111` está vinculado (resolve para `user-a`).
    Qualquer outro número não tem vínculo (`None`).
    """
    calls: dict[str, list[str]] = {"resolve": [], "thread": []}

    async def _fake_resolve(phone_number: str) -> str | None:
        calls["resolve"].append(phone_number)
        return "user-a" if phone_number == _LINKED_PHONE else None

    def _fake_get_or_create_thread_id(phone_number: str) -> str:
        calls["thread"].append(phone_number)
        return "thread-xyz"

    monkeypatch.setattr(whatsapp_webhook_router, "resolve_whatsapp_user_id", _fake_resolve)
    monkeypatch.setattr(
        whatsapp_webhook_router, "get_or_create_thread_id", _fake_get_or_create_thread_id
    )
    return calls


# ============================================================================
# Unit-1 — REQ-004 (whatsapp-channel delta) cenário "Roteamento normal"
# ============================================================================


async def test_non_slash_message_is_routed_normally_after_authorization(
    resolution_calls: dict[str, list[str]],
    agent_runner_recorder: _RecordingAgentRunner,
    dispatch_command_mock: AsyncMock,
    link_code_repo: _FakeWhatsAppLinkCodeRepository,
    user_integration_repo: _FakeUserIntegrationRepository,
) -> None:
    """Mensagem autorizada cujo text NÃO é slash command.

    `commands.dispatch_command` é chamado e retorna `False` (texto não é
    slash command); o roteamento segue normalmente e `AgentRunnerPort.run()`
    é chamado.
    """
    dispatch_command_mock.return_value = False
    payload = _sample_messages_upsert_payload(text="olá", phone_number=_LINKED_PHONE)
    request = _FakeRequest(payload)

    result = await whatsapp_webhook_router.whatsapp_webhook_endpoint(
        token=_TOKEN,
        request=request,
        link_codes=link_code_repo,
        user_integrations=user_integration_repo,
        agent_runner=agent_runner_recorder,
    )

    assert result == {"received": True}
    assert resolution_calls["resolve"] == [_LINKED_PHONE]
    # thread_id é resolvido quando dispatch_command retorna False (não era
    # slash command) — o caminho normal para o agente precisa.
    assert resolution_calls["thread"] == [_LINKED_PHONE]

    # `commands.dispatch_command` foi chamado com (text, phone, instance).
    dispatch_command_mock.assert_awaited_once_with(
        "olá", _LINKED_PHONE, "jeff-ai-central"
    )

    # E `agent_runner.run` foi chamado exatamente uma vez, com o thread_id
    # resolvido.
    assert len(agent_runner_recorder.calls) == 1
    assert agent_runner_recorder.calls[0]["thread_id"] == "thread-xyz"


# ============================================================================
# Unit-2 — REQ-004 (whatsapp-channel delta) cenário "slash command não roteam agente"
# ============================================================================


async def test_slash_command_message_skips_agent_run(
    resolution_calls: dict[str, list[str]],
    agent_runner_recorder: _RecordingAgentRunner,
    dispatch_command_mock: AsyncMock,
    link_code_repo: _FakeWhatsAppLinkCodeRepository,
    user_integration_repo: _FakeUserIntegrationRepository,
) -> None:
    """Mensagem autorizada cujo text É slash command (ex.: `/sessions`).

    `commands.dispatch_command` é chamado e retorna `True`; o fluxo
    termina ali — `AgentRunnerPort.run()` NÃO é chamado, e a resolução de
    `thread_id` também NÃO é tocada (slash commands não precisam).
    """
    dispatch_command_mock.return_value = True
    payload = _sample_messages_upsert_payload(
        text="/sessions", phone_number=_LINKED_PHONE
    )
    request = _FakeRequest(payload)

    result = await whatsapp_webhook_router.whatsapp_webhook_endpoint(
        token=_TOKEN,
        request=request,
        link_codes=link_code_repo,
        user_integrations=user_integration_repo,
        agent_runner=agent_runner_recorder,
    )

    assert result == {"received": True}
    assert resolution_calls["resolve"] == [_LINKED_PHONE]
    # thread_id NÃO foi resolvido — slash commands short-circuit antes.
    assert resolution_calls["thread"] == []

    dispatch_command_mock.assert_awaited_once_with(
        "/sessions", _LINKED_PHONE, "jeff-ai-central"
    )

    # Nenhuma chamada a agent_runner.run.
    assert agent_runner_recorder.calls == []


# ============================================================================
# Unit-3 — REQ-006 (whatsapp-slash-commands) cenário "slash command de número não vinculado"
# ============================================================================


async def test_unlinked_phone_number_blocks_dispatch_and_agent(
    resolution_calls: dict[str, list[str]],
    agent_runner_recorder: _RecordingAgentRunner,
    dispatch_command_mock: AsyncMock,
    link_code_repo: _FakeWhatsAppLinkCodeRepository,
    user_integration_repo: _FakeUserIntegrationRepository,
) -> None:
    """Slash command de número SEM vínculo ativo é descartado.

    Ordem do router: resolve_whatsapp_user_id → se None, retorno silencioso.
    `commands.dispatch_command` e `AgentRunnerPort.run` não rodam.
    """
    payload = _sample_messages_upsert_payload(
        text="/sessions", phone_number=_UNLINKED_PHONE
    )
    request = _FakeRequest(payload)

    result = await whatsapp_webhook_router.whatsapp_webhook_endpoint(
        token=_TOKEN,
        request=request,
        link_codes=link_code_repo,
        user_integrations=user_integration_repo,
        agent_runner=agent_runner_recorder,
    )

    assert result == {"received": True}
    assert resolution_calls["resolve"] == [_UNLINKED_PHONE]
    # thread_id nunca é resolvido.
    assert resolution_calls["thread"] == []

    # Nada chamado: dispatcher nem runner.
    dispatch_command_mock.assert_not_called()
    assert agent_runner_recorder.calls == []
