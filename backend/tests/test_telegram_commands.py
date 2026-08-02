"""Testes de `src/infrastructure/telegram/commands.py` (slash commands).

Cobre a task `telegram-slash-commands-task-commands-1`:

- REQ-001 (spec `telegram-slash-commands`): pré-processamento — mensagem sem
  `/` é ignorada por `dispatch_command`; mensagem com `/` roteia para o
  handler local correspondente, nunca para o agente.
- REQ-002: `/new [título]` cria e ativa uma nova thread.
- REQ-003: `/title [título]` lê ou altera o título da thread ativa.
- REQ-004: `/resume [id-ou-título]` troca a thread ativa por id ou título,
  rejeitando ids de outro chat sem vazar a qual chat pertencem.
- REQ-005: `/sessions` lista as threads do chat, marcando a ativa.
- REQ-006: a allowlist de `chat_id` é aplicada antes do dispatch.

Os handlers são testados via mock das funções de `thread_repository`
importadas em `commands.py` (o comportamento do próprio `thread_repository`
já está coberto por `test_telegram_thread_repository.py`) — aqui o alvo é a
orquestração: quais funções são chamadas, com quais argumentos, e o que é
respondido ao chat.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from src.infrastructure.telegram import commands


class _FakeBot:
    """Bot fake: registra `send_message` em `self.sent` sem tocar a rede."""

    def __init__(self) -> None:
        self.sent: list[tuple[Any, str]] = []

    async def send_message(
        self, chat_id: Any, text: str, *args: Any, **kwargs: Any
    ) -> str:  # noqa: ANN401
        self.sent.append((chat_id, text))
        return "message-sent"


def _make_update(chat_id: Any, text: str) -> MagicMock:
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message.text = text
    return update


# ---------------------------------------------------------------------------
# dispatch_command — REQ-001 pré-processamento
# ---------------------------------------------------------------------------


async def test_dispatch_command_ignores_non_slash_text() -> None:
    bot = _FakeBot()
    dispatch = commands.make_command_dispatcher(authorized_chat_id="123", bot=bot)
    update = _make_update("123", "olá")

    await dispatch(update, MagicMock())

    assert bot.sent == []


async def test_dispatch_command_routes_slash_command_to_handler(
    monkeypatch: Any,
) -> None:
    bot = _FakeBot()
    list_mock = MagicMock(return_value=[])
    monkeypatch.setattr(commands, "list_threads_for_chat", list_mock)
    dispatch = commands.make_command_dispatcher(authorized_chat_id="123", bot=bot)
    update = _make_update("123", "/sessions")

    await dispatch(update, MagicMock())

    list_mock.assert_called_once_with("123")
    assert len(bot.sent) == 1


# ---------------------------------------------------------------------------
# handle_new — REQ-002
# ---------------------------------------------------------------------------


async def test_handle_new_without_title_creates_thread_and_responds_with_id(
    monkeypatch: Any,
) -> None:
    bot = _FakeBot()
    create_mock = MagicMock(return_value="thread-abc")
    monkeypatch.setattr(commands, "create_thread_for_chat", create_mock)

    await commands.handle_new("123", "", bot)

    create_mock.assert_called_once_with("123", None)
    assert len(bot.sent) == 1
    assert "thread-abc" in bot.sent[0][1]


async def test_handle_new_with_title_creates_thread_and_confirms_title(
    monkeypatch: Any,
) -> None:
    bot = _FakeBot()
    create_mock = MagicMock(return_value="thread-abc")
    monkeypatch.setattr(commands, "create_thread_for_chat", create_mock)

    await commands.handle_new("123", "pagamentos", bot)

    create_mock.assert_called_once_with("123", "pagamentos")
    assert "pagamentos" in bot.sent[0][1]


async def test_handle_new_duplicate_title_rejects_without_inserting(
    monkeypatch: Any,
) -> None:
    bot = _FakeBot()
    create_mock = MagicMock(side_effect=ValueError("título já em uso"))
    monkeypatch.setattr(commands, "create_thread_for_chat", create_mock)

    await commands.handle_new("123", "pagamentos", bot)

    create_mock.assert_called_once_with("123", "pagamentos")
    assert len(bot.sent) == 1
    assert "em uso" in bot.sent[0][1]


# ---------------------------------------------------------------------------
# handle_title — REQ-003
# ---------------------------------------------------------------------------


async def test_handle_title_with_argument_updates_active_thread(
    monkeypatch: Any,
) -> None:
    bot = _FakeBot()
    monkeypatch.setattr(commands, "get_or_create_thread_id", MagicMock(return_value="T1"))
    update_mock = MagicMock(return_value=True)
    monkeypatch.setattr(commands, "update_thread_title", update_mock)

    await commands.handle_title("123", "projeto de refactor", bot)

    update_mock.assert_called_once_with("T1", "123", "projeto de refactor")
    assert "projeto de refactor" in bot.sent[0][1]


async def test_handle_title_without_argument_reports_current_title(
    monkeypatch: Any,
) -> None:
    bot = _FakeBot()
    monkeypatch.setattr(commands, "get_or_create_thread_id", MagicMock(return_value="T1"))
    monkeypatch.setattr(
        commands,
        "list_threads_for_chat",
        MagicMock(
            return_value=[
                {"thread_id": "T1", "title": "pagamentos", "active": True, "created_at": None}
            ]
        ),
    )
    update_mock = MagicMock()
    monkeypatch.setattr(commands, "update_thread_title", update_mock)

    await commands.handle_title("123", "", bot)

    update_mock.assert_not_called()
    assert "pagamentos" in bot.sent[0][1]


async def test_handle_title_without_argument_and_without_title_reports_placeholder(
    monkeypatch: Any,
) -> None:
    bot = _FakeBot()
    monkeypatch.setattr(commands, "get_or_create_thread_id", MagicMock(return_value="T1"))
    monkeypatch.setattr(
        commands,
        "list_threads_for_chat",
        MagicMock(
            return_value=[{"thread_id": "T1", "title": None, "active": True, "created_at": None}]
        ),
    )

    await commands.handle_title("123", "", bot)

    assert "<sem título>" in bot.sent[0][1]


async def test_handle_title_duplicate_rejects_without_changing_active_title(
    monkeypatch: Any,
) -> None:
    bot = _FakeBot()
    monkeypatch.setattr(commands, "get_or_create_thread_id", MagicMock(return_value="T1"))
    update_mock = MagicMock(side_effect=ValueError("duplicado"))
    monkeypatch.setattr(commands, "update_thread_title", update_mock)

    await commands.handle_title("123", "pagamentos", bot)

    update_mock.assert_called_once_with("T1", "123", "pagamentos")
    assert "em uso" in bot.sent[0][1]


# ---------------------------------------------------------------------------
# handle_resume — REQ-004
# ---------------------------------------------------------------------------


async def test_handle_resume_by_thread_id_sets_active(monkeypatch: Any) -> None:
    bot = _FakeBot()
    monkeypatch.setattr(
        commands,
        "list_threads_for_chat",
        MagicMock(
            return_value=[
                {"thread_id": "1111-aaaa", "title": None, "active": False, "created_at": None},
                {"thread_id": "T2", "title": None, "active": True, "created_at": None},
            ]
        ),
    )
    set_active_mock = MagicMock(return_value=True)
    monkeypatch.setattr(commands, "set_active_thread", set_active_mock)

    await commands.handle_resume("123", "1111-aaaa", bot)

    set_active_mock.assert_called_once_with("123", "1111-aaaa")
    assert len(bot.sent) == 1


async def test_handle_resume_by_title_sets_active(monkeypatch: Any) -> None:
    bot = _FakeBot()
    monkeypatch.setattr(
        commands,
        "get_thread_by_title",
        MagicMock(
            return_value={
                "thread_id": "T1",
                "title": "pagamentos",
                "active": False,
                "created_at": None,
            }
        ),
    )
    set_active_mock = MagicMock(return_value=True)
    monkeypatch.setattr(commands, "set_active_thread", set_active_mock)

    await commands.handle_resume("123", "pagamentos", bot)

    set_active_mock.assert_called_once_with("123", "T1")
    assert "pagamentos" in bot.sent[0][1]


async def test_handle_resume_by_id_from_other_chat_is_rejected_without_leaking(
    monkeypatch: Any,
) -> None:
    bot = _FakeBot()
    # `list_threads_for_chat("123")` não devolve a thread de outro chat.
    monkeypatch.setattr(commands, "list_threads_for_chat", MagicMock(return_value=[]))
    set_active_mock = MagicMock()
    monkeypatch.setattr(commands, "set_active_thread", set_active_mock)

    await commands.handle_resume("123", "cross-chat-uuid", bot)

    set_active_mock.assert_not_called()
    message = bot.sent[0][1]
    assert "456" not in message
    assert "outro chat" not in message


async def test_handle_resume_without_argument_reports_active_thread(
    monkeypatch: Any,
) -> None:
    bot = _FakeBot()
    monkeypatch.setattr(commands, "get_or_create_thread_id", MagicMock(return_value="T1"))
    monkeypatch.setattr(
        commands,
        "list_threads_for_chat",
        MagicMock(
            return_value=[
                {"thread_id": "T1", "title": "pagamentos", "active": True, "created_at": None}
            ]
        ),
    )
    set_active_mock = MagicMock()
    monkeypatch.setattr(commands, "set_active_thread", set_active_mock)

    await commands.handle_resume("123", "", bot)

    set_active_mock.assert_not_called()
    message = bot.sent[0][1]
    assert "T1" in message
    assert "pagamentos" in message


# ---------------------------------------------------------------------------
# handle_sessions — REQ-005
# ---------------------------------------------------------------------------


async def test_handle_sessions_lists_threads_marking_active(monkeypatch: Any) -> None:
    bot = _FakeBot()
    monkeypatch.setattr(
        commands,
        "list_threads_for_chat",
        MagicMock(
            return_value=[
                {"thread_id": "T1", "title": "a", "active": False, "created_at": None},
                {"thread_id": "T2", "title": "b", "active": True, "created_at": None},
                {"thread_id": "T3", "title": None, "active": False, "created_at": None},
            ]
        ),
    )

    await commands.handle_sessions("123", "", bot)

    message = bot.sent[0][1]
    assert "T1" in message
    assert "T2" in message
    assert "T3" in message
    assert "*" in message


async def test_handle_sessions_without_threads_reports_hint(monkeypatch: Any) -> None:
    bot = _FakeBot()
    monkeypatch.setattr(commands, "list_threads_for_chat", MagicMock(return_value=[]))

    await commands.handle_sessions("123", "", bot)

    assert "nenhuma thread" in bot.sent[0][1].lower()


# ---------------------------------------------------------------------------
# dispatch_command allowlist — REQ-006
# ---------------------------------------------------------------------------


async def test_dispatch_command_drops_unauthorized_chat(monkeypatch: Any) -> None:
    bot = _FakeBot()
    list_mock = MagicMock()
    monkeypatch.setattr(commands, "list_threads_for_chat", list_mock)
    dispatch = commands.make_command_dispatcher(authorized_chat_id="999", bot=bot)
    update = _make_update("123", "/sessions")

    await dispatch(update, MagicMock())

    assert bot.sent == []
    list_mock.assert_not_called()
