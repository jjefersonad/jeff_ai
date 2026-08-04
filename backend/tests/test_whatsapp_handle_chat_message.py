"""Testes do webhook WhatsApp → `HandleChatMessage` (task
`unify-message-delivery-pipeline-task-whatsapp-1`).

Cobre REQ-006 (whatsapp-channel): ramo normal chama o caso de uso; slash
commands continuam no dispatcher.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.infrastructure.web.whatsapp_webhook_router as whatsapp_webhook_router
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.application.ports.whatsapp_link_code_repository import (
    WhatsAppLinkCodeRepositoryPort,
)
from src.domain.integrations import UserIntegration, WhatsAppLinkCode
from src.infrastructure.channels.whatsapp_channel import WhatsAppChannel
from src.infrastructure.usage.user_key import whatsapp_user_key


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


def _sample_payload(*, text: str, phone_number: str) -> dict[str, object]:
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
def _authorize_linked_phone(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_resolve(phone_number: str) -> str | None:
        return "user-a" if phone_number == _LINKED_PHONE else None

    def _fake_thread(phone_number: str) -> str:
        return "thread-xyz"

    monkeypatch.setattr(whatsapp_webhook_router, "resolve_whatsapp_user_id", _fake_resolve)
    monkeypatch.setattr(
        whatsapp_webhook_router, "get_or_create_thread_id", _fake_thread
    )


@pytest.mark.asyncio
async def test_normal_message_calls_handle_chat_message_not_route_authorized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-1: mensagem normal autorizada → `HandleChatMessage.execute` uma vez."""
    user_text = "olá do whatsapp"
    dispatch_mock = AsyncMock(return_value=False)
    fake_commands = MagicMock()
    fake_commands.dispatch_command = dispatch_mock
    monkeypatch.setattr(whatsapp_webhook_router, "commands", fake_commands)

    agent_runner = MagicMock()
    agent_runner.run = AsyncMock()

    execute_mock = AsyncMock()
    with patch(
        "src.infrastructure.web.whatsapp_webhook_router.HandleChatMessage"
    ) as handle_cls:
        handle_cls.return_value.execute = execute_mock

        result = await whatsapp_webhook_router.whatsapp_webhook_endpoint(
            token=_TOKEN,
            request=_FakeRequest(
                _sample_payload(text=user_text, phone_number=_LINKED_PHONE)
            ),
            link_codes=_FakeWhatsAppLinkCodeRepository(),
            user_integrations=_FakeUserIntegrationRepository(),
            agent_runner=agent_runner,
        )

    assert result == {"received": True}
    assert not hasattr(whatsapp_webhook_router, "route_authorized_message")
    handle_cls.assert_called_once_with(agent_runner=agent_runner)
    execute_mock.assert_awaited_once()
    kwargs = execute_mock.await_args.kwargs
    assert isinstance(kwargs["channel"], WhatsAppChannel)
    assert kwargs["user_key"] == whatsapp_user_key(_LINKED_PHONE)
    assert kwargs["thread_id"] == "thread-xyz"
    assert kwargs["text"] == user_text
    agent_runner.run.assert_not_called()


@pytest.mark.asyncio
async def test_slash_command_skips_handle_chat_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-2: `/sessions` → `dispatch_command`; sem `HandleChatMessage`."""
    dispatch_mock = AsyncMock(return_value=True)
    fake_commands = MagicMock()
    fake_commands.dispatch_command = dispatch_mock
    monkeypatch.setattr(whatsapp_webhook_router, "commands", fake_commands)

    agent_runner = MagicMock()
    agent_runner.run = AsyncMock()

    execute_mock = AsyncMock()
    with patch(
        "src.infrastructure.web.whatsapp_webhook_router.HandleChatMessage"
    ) as handle_cls:
        handle_cls.return_value.execute = execute_mock

        result = await whatsapp_webhook_router.whatsapp_webhook_endpoint(
            token=_TOKEN,
            request=_FakeRequest(
                _sample_payload(text="/sessions", phone_number=_LINKED_PHONE)
            ),
            link_codes=_FakeWhatsAppLinkCodeRepository(),
            user_integrations=_FakeUserIntegrationRepository(),
            agent_runner=agent_runner,
        )

    assert result == {"received": True}
    dispatch_mock.assert_awaited_once_with(
        "/sessions", _LINKED_PHONE, "jeff-ai-central"
    )
    execute_mock.assert_not_awaited()
    handle_cls.assert_not_called()
    agent_runner.run.assert_not_called()
