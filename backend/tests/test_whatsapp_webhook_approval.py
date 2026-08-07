"""Testes da interceptação de resposta de aprovação pendente no webhook WhatsApp.

Cobre a task `whatsapp-tool-approval-task-webhook-3`:

- Unit-1 (REQ-009 cenário 1): resposta "Aprovar" de um `phone_number` com
  aprovação pendente resume o grafo com `{"type": "approve"}` e limpa a
  pendência.
- Unit-2 (REQ-009 cenário 2): idem para "Rejeitar" → `{"type": "reject"}`.
- Unit-3 (REQ-011 cenário 1): sem pendência para o `phone_number`, a
  resposta não é tratada como decisão — `agent_runner.resume` NÃO é
  chamado, e a mensagem segue para o roteamento normal (aqui,
  `commands.dispatch_command` + `agent_runner.run`, mesmo padrão de
  `test_whatsapp_webhook_slash_commands.py`).

Mesma técnica de `test_whatsapp_webhook_slash_commands.py`: chama
`whatsapp_webhook_endpoint` diretamente (sem `TestClient`) para não
acoplar ao grafo de rotas completo do `webapp.py`.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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
from src.infrastructure.whatsapp import approval


class _RecordingAgentRunner:
    """`AgentRunnerPort` fake — registra chamadas a `run` E `resume`."""

    def __init__(self) -> None:
        self.run_calls: list[dict[str, Any]] = []
        self.resume_calls: list[dict[str, Any]] = []

    async def run(self, **kwargs: Any) -> AgentRunResult:
        self.run_calls.append(kwargs)
        return AgentRunResult(thread_id=kwargs["thread_id"], status="ok")

    async def resume(self, **kwargs: Any) -> AgentRunResult:
        self.resume_calls.append(kwargs)
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


@pytest.fixture(autouse=True)
def _evolution_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVOLUTION_API_URL", "http://evolution_api:8080")
    monkeypatch.setenv("EVOLUTION_API_KEY", "fake-key")
    monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "jeff-ai-central")
    monkeypatch.setenv("EVOLUTION_WEBHOOK_TOKEN", _TOKEN)


@pytest.fixture(autouse=True)
def _clear_pending_approvals() -> None:
    approval.clear_pending_approval(_LINKED_PHONE)
    yield
    approval.clear_pending_approval(_LINKED_PHONE)


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
    mock = AsyncMock(return_value=False)
    fake_commands = MagicMock()
    fake_commands.dispatch_command = mock
    monkeypatch.setattr(whatsapp_webhook_router, "commands", fake_commands)
    return mock


@pytest.fixture
def resolution_calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
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


async def _call_endpoint(
    *,
    text: str,
    link_code_repo: _FakeWhatsAppLinkCodeRepository,
    user_integration_repo: _FakeUserIntegrationRepository,
    agent_runner_recorder: _RecordingAgentRunner,
) -> dict[str, bool]:
    payload = _sample_messages_upsert_payload(text=text, phone_number=_LINKED_PHONE)
    request = _FakeRequest(payload)
    return await whatsapp_webhook_router.whatsapp_webhook_endpoint(
        token=_TOKEN,
        request=request,
        link_codes=link_code_repo,
        user_integrations=user_integration_repo,
        agent_runner=agent_runner_recorder,
    )


# ============================================================================
# Unit-1 — REQ-009 cenário 1: "Aprovar" resume approve e limpa a pendência
# ============================================================================


async def test_approve_reply_resumes_with_approve_decision_and_clears_pending(
    resolution_calls: dict[str, list[str]],
    agent_runner_recorder: _RecordingAgentRunner,
    dispatch_command_mock: AsyncMock,
    link_code_repo: _FakeWhatsAppLinkCodeRepository,
    user_integration_repo: _FakeUserIntegrationRepository,
) -> None:
    approval.set_pending_approval(
        _LINKED_PHONE,
        approval.PendingApproval(
            thread_id="thread-pending-1",
            action_requests=({"name": "edit_file"},),
            review_configs=({"allowed_decisions": ["approve", "reject"]},),
        ),
    )

    result = await _call_endpoint(
        text="Aprovar",
        link_code_repo=link_code_repo,
        user_integration_repo=user_integration_repo,
        agent_runner_recorder=agent_runner_recorder,
    )

    assert result == {"received": True}
    assert len(agent_runner_recorder.resume_calls) == 1
    call = agent_runner_recorder.resume_calls[0]
    assert call["thread_id"] == "thread-pending-1"
    assert call["decisions"] == ({"type": "approve"},)

    assert approval.get_pending_approval(_LINKED_PHONE) is None
    # Não deve ter caído no roteamento normal.
    dispatch_command_mock.assert_not_called()
    assert agent_runner_recorder.run_calls == []


# ============================================================================
# Unit-2 — REQ-009 cenário 2: "Rejeitar" resume reject e limpa a pendência
# ============================================================================


async def test_reject_reply_resumes_with_reject_decision_and_clears_pending(
    resolution_calls: dict[str, list[str]],
    agent_runner_recorder: _RecordingAgentRunner,
    dispatch_command_mock: AsyncMock,
    link_code_repo: _FakeWhatsAppLinkCodeRepository,
    user_integration_repo: _FakeUserIntegrationRepository,
) -> None:
    approval.set_pending_approval(
        _LINKED_PHONE,
        approval.PendingApproval(
            thread_id="thread-pending-2",
            action_requests=({"name": "git_commit"},),
            review_configs=({"allowed_decisions": ["approve", "reject"]},),
        ),
    )

    result = await _call_endpoint(
        text="Rejeitar",
        link_code_repo=link_code_repo,
        user_integration_repo=user_integration_repo,
        agent_runner_recorder=agent_runner_recorder,
    )

    assert result == {"received": True}
    assert len(agent_runner_recorder.resume_calls) == 1
    call = agent_runner_recorder.resume_calls[0]
    assert call["thread_id"] == "thread-pending-2"
    assert call["decisions"] == ({"type": "reject"},)

    assert approval.get_pending_approval(_LINKED_PHONE) is None
    dispatch_command_mock.assert_not_called()
    assert agent_runner_recorder.run_calls == []


# ============================================================================
# Unit-3 — REQ-011 cenário 1: sem pendência, cai no roteamento normal
# ============================================================================


async def test_no_pending_approval_falls_through_to_normal_routing(
    resolution_calls: dict[str, list[str]],
    agent_runner_recorder: _RecordingAgentRunner,
    dispatch_command_mock: AsyncMock,
    link_code_repo: _FakeWhatsAppLinkCodeRepository,
    user_integration_repo: _FakeUserIntegrationRepository,
) -> None:
    assert approval.get_pending_approval(_LINKED_PHONE) is None

    result = await _call_endpoint(
        text="Aprovar",
        link_code_repo=link_code_repo,
        user_integration_repo=user_integration_repo,
        agent_runner_recorder=agent_runner_recorder,
    )

    assert result == {"received": True}
    assert agent_runner_recorder.resume_calls == []
    # Sem pendência, "Aprovar" é só uma mensagem normal — segue roteamento.
    dispatch_command_mock.assert_awaited_once_with("Aprovar", _LINKED_PHONE, "jeff-ai-central")
    assert len(agent_runner_recorder.run_calls) == 1


# ============================================================================
# Unit-4 — REQ-010 cenário 1 (task-webhook-4): "Ajustar" marca awaiting_edit_text
# ============================================================================


async def test_adjust_reply_marks_awaiting_edit_text_and_prompts(
    resolution_calls: dict[str, list[str]],
    agent_runner_recorder: _RecordingAgentRunner,
    dispatch_command_mock: AsyncMock,
    link_code_repo: _FakeWhatsAppLinkCodeRepository,
    user_integration_repo: _FakeUserIntegrationRepository,
) -> None:
    approval.set_pending_approval(
        _LINKED_PHONE,
        approval.PendingApproval(
            thread_id="thread-pending-3",
            action_requests=({"name": "edit_file"},),
            review_configs=({"allowed_decisions": ["approve", "reject"]},),
        ),
    )

    with patch(
        "src.infrastructure.whatsapp.approval.evolution_client.send_text",
        new_callable=AsyncMock,
    ) as send_text_mock:
        result = await _call_endpoint(
            text="Ajustar",
            link_code_repo=link_code_repo,
            user_integration_repo=user_integration_repo,
            agent_runner_recorder=agent_runner_recorder,
        )

    assert result == {"received": True}
    # Não resume ainda — só marca o flag e pede o texto do ajuste.
    assert agent_runner_recorder.resume_calls == []
    pending = approval.get_pending_approval(_LINKED_PHONE)
    assert pending is not None
    assert pending.awaiting_edit_text is True
    send_text_mock.assert_awaited_once()
    args, _ = send_text_mock.await_args
    assert args[0] == "jeff-ai-central"
    assert args[1] == _LINKED_PHONE
    dispatch_command_mock.assert_not_called()
    assert agent_runner_recorder.run_calls == []


# ============================================================================
# Unit-5 — REQ-010 cenário 1 (task-webhook-4): próxima mensagem resolve reject+message
# ============================================================================


async def test_next_text_after_adjust_resolves_reject_with_feedback(
    resolution_calls: dict[str, list[str]],
    agent_runner_recorder: _RecordingAgentRunner,
    dispatch_command_mock: AsyncMock,
    link_code_repo: _FakeWhatsAppLinkCodeRepository,
    user_integration_repo: _FakeUserIntegrationRepository,
) -> None:
    approval.set_pending_approval(
        _LINKED_PHONE,
        approval.PendingApproval(
            thread_id="thread-pending-4",
            action_requests=({"name": "edit_file"},),
            review_configs=({"allowed_decisions": ["approve", "reject"]},),
            awaiting_edit_text=True,
        ),
    )

    result = await _call_endpoint(
        text="troque a cor para azul",
        link_code_repo=link_code_repo,
        user_integration_repo=user_integration_repo,
        agent_runner_recorder=agent_runner_recorder,
    )

    assert result == {"received": True}
    assert len(agent_runner_recorder.resume_calls) == 1
    call = agent_runner_recorder.resume_calls[0]
    assert call["thread_id"] == "thread-pending-4"
    assert call["decisions"] == ({"type": "reject", "message": "troque a cor para azul"},)

    assert approval.get_pending_approval(_LINKED_PHONE) is None
    # Não deve ter sido roteada como conversa normal nem slash command.
    dispatch_command_mock.assert_not_called()
    assert agent_runner_recorder.run_calls == []
