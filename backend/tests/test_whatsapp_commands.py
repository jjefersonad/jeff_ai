"""Testes de `src/infrastructure/whatsapp/commands.py` (slash commands).

Cobre a task `whatsapp-slash-commands-task-commands-1`:

- REQ-001 (spec `whatsapp-slash-commands`): pré-processamento — mensagem sem
  `/` é ignorada por `dispatch_command`; mensagem com `/` roteia para o
  handler local correspondente, nunca para o agente.
- REQ-002: `/new [título]` cria e ativa uma nova thread.
- REQ-003: `/title [título]` lê ou altera o título da thread ativa.
- REQ-004: `/resume [id-ou-título]` troca a thread ativa por id ou título,
  rejeitando ids de outro número sem vazar a qual número pertencem.
- REQ-005: `/sessions` lista as threads do número, marcando a ativa.

Padrão: os handlers são testados via mock das funções de `thread_repository`
importadas em `commands.py` (o comportamento do próprio `thread_repository`
já está coberto por `test_whatsapp_thread_repository.py`) — aqui o alvo é a
orquestração: quais funções são chamadas, com quais argumentos, e o que é
respondido via `evolution_client.send_text(instance, phone_number, text)`.

A allowlist de `phone_number` (REQ-006 do whatsapp-slash-commands-spec) é
garantida pela ordem de chamada em `whatsapp_webhook_router.py` — não é
responsabilidade deste módulo (não há `is_authorized_phone_number` em
`authorization.py` para replicar o padrão do Telegram, e a tarefa
`channel-1` ainda será implementada para forçar essa ordem).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.whatsapp import commands


# ============================================================================
# Fakes — paralelos a `_FakeBot` em test_telegram_commands.py.
# ============================================================================


class _FakeEvolution:
    """Cliente fake: registra `send_text` em `self.sent` sem tocar a rede."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def send_text(self, instance: str, phone_number: str, text: str) -> None:
        self.sent.append((instance, phone_number, text))


@pytest.fixture
def fake_evolution(monkeypatch: pytest.MonkeyPatch) -> _FakeEvolution:
    """Fornece um `_FakeEvolution` já registrado como `commands.send_text`."""
    fake = _FakeEvolution()
    monkeypatch.setattr(commands, "send_text", fake.send_text)
    return fake


# ============================================================================
# dispatch_command — REQ-001 pré-processamento
# ============================================================================


async def test_dispatch_command_returns_false_for_plain_text(
    monkeypatch: Any,
) -> None:
    """Unit-1: mensagem normal (sem `/`) — dispatch retorna False, nada é chamado."""
    fake = _FakeEvolution()
    monkeypatch.setattr(commands, "send_text", fake.send_text)
    handle_sessions_mock = AsyncMock()
    monkeypatch.setattr(commands, "handle_sessions", handle_sessions_mock)

    result = await commands.dispatch_command("olá", "5511999990000", "inst-1")

    assert result is False
    handle_sessions_mock.assert_not_called()
    assert fake.sent == []


async def test_dispatch_command_dispatches_slash_command_to_handler(
    monkeypatch: Any,
) -> None:
    """Unit-2: mensagem com `/` — handler de `/sessions` é chamado e retorna True."""
    handle_sessions_mock = AsyncMock()
    monkeypatch.setattr(commands, "handle_sessions", handle_sessions_mock)

    result = await commands.dispatch_command("/sessions", "5511999990000", "inst-1")

    assert result is True
    handle_sessions_mock.assert_awaited_once_with(
        "5511999990000", "", "inst-1"
    )


# ============================================================================
# handle_new — REQ-002
# ============================================================================


async def test_handle_new_without_title_creates_thread_and_responds_with_id(
    fake_evolution: _FakeEvolution,
    monkeypatch: Any,
) -> None:
    """Unit-3: `/new` sem título cria thread nova (title=None) e responde com o id."""
    create_mock = MagicMock(return_value="thread-abc")
    monkeypatch.setattr(commands, "create_thread_for_number", create_mock)

    await commands.handle_new("5511999990000", "", "inst-1")

    create_mock.assert_called_once_with("5511999990000", None)
    assert len(fake_evolution.sent) == 1
    instance, phone, text = fake_evolution.sent[0]
    assert instance == "inst-1"
    assert phone == "5511999990000"
    assert "thread-abc" in text


async def test_handle_new_with_title_passes_title_to_repository(
    fake_evolution: _FakeEvolution,
    monkeypatch: Any,
) -> None:
    """Unit-4: `/new pagamentos` cria thread com title='pagamentos' e confirma."""
    create_mock = MagicMock(return_value="thread-xyz")
    monkeypatch.setattr(commands, "create_thread_for_number", create_mock)

    await commands.handle_new("5511999990000", "pagamentos", "inst-1")

    create_mock.assert_called_once_with("5511999990000", "pagamentos")
    assert len(fake_evolution.sent) == 1
    _, _, text = fake_evolution.sent[0]
    assert "pagamentos" in text


async def test_handle_new_catches_duplicate_title_and_responds_with_conflict(
    fake_evolution: _FakeEvolution,
    monkeypatch: Any,
) -> None:
    """Unit-5: `/new pagamentos` quando title já existe — responde com conflito, não propaga."""
    create_mock = MagicMock(side_effect=ValueError("duplicate title"))
    monkeypatch.setattr(commands, "create_thread_for_number", create_mock)

    await commands.handle_new("5511999990000", "pagamentos", "inst-1")

    create_mock.assert_called_once_with("5511999990000", "pagamentos")
    assert len(fake_evolution.sent) == 1
    _, _, text = fake_evolution.sent[0]
    # Mensagem clara de conflito (sem revelar stack trace, sem propagar).
    assert "pagamentos" in text
    # Garantia adicional: nada de "[id ...]" — sem thread criada.
    assert "id " not in text.lower() and "id_" not in text.lower()


# ============================================================================
# handle_title — REQ-003
# ============================================================================


async def test_handle_title_with_argument_updates_title_and_confirms(
    fake_evolution: _FakeEvolution,
    monkeypatch: Any,
) -> None:
    """Unit-6: `/title projeto de refactor` chama get_or_create + update e responde."""
    get_active_mock = MagicMock(return_value="thread-1")
    monkeypatch.setattr(commands, "get_or_create_thread_id", get_active_mock)
    update_mock = MagicMock(return_value=True)
    monkeypatch.setattr(commands, "update_thread_title", update_mock)

    await commands.handle_title("5511999990000", "projeto de refactor", "inst-1")

    get_active_mock.assert_called_once_with("5511999990000")
    update_mock.assert_called_once_with("thread-1", "5511999990000", "projeto de refactor")
    assert len(fake_evolution.sent) == 1
    _, _, text = fake_evolution.sent[0]
    assert "projeto de refactor" in text


async def test_handle_title_without_argument_responds_with_current_title(
    fake_evolution: _FakeEvolution,
    monkeypatch: Any,
) -> None:
    """Unit-7: `/title` (sem args) responde com o título atual da thread ativa."""
    get_active_mock = MagicMock(return_value="thread-1")
    monkeypatch.setattr(commands, "get_or_create_thread_id", get_active_mock)
    update_mock = MagicMock(return_value=True)
    monkeypatch.setattr(commands, "update_thread_title", update_mock)

    # list_threads_for_number é usado por _find_thread para descobrir o title atual.
    list_mock = MagicMock(
        return_value=[{"thread_id": "thread-1", "title": "pagamentos", "active": True}]
    )
    monkeypatch.setattr(commands, "list_threads_for_number", list_mock)

    await commands.handle_title("5511999990000", "", "inst-1")

    get_active_mock.assert_called_once_with("5511999990000")
    list_mock.assert_called_once_with("5511999990000")
    update_mock.assert_not_called()
    assert len(fake_evolution.sent) == 1
    _, _, text = fake_evolution.sent[0]
    assert "pagamentos" in text


async def test_handle_title_catches_duplicate_and_responds_with_conflict(
    fake_evolution: _FakeEvolution,
    monkeypatch: Any,
) -> None:
    """Unit-8: `/title X` quando X já é título de outra thread — responde com conflito."""
    get_active_mock = MagicMock(return_value="thread-1")
    monkeypatch.setattr(commands, "get_or_create_thread_id", get_active_mock)
    update_mock = MagicMock(side_effect=ValueError("duplicate title"))
    monkeypatch.setattr(commands, "update_thread_title", update_mock)

    await commands.handle_title("5511999990000", "pagamentos", "inst-1")

    update_mock.assert_called_once_with("thread-1", "5511999990000", "pagamentos")
    assert len(fake_evolution.sent) == 1
    _, _, text = fake_evolution.sent[0]
    assert "pagamentos" in text


# ============================================================================
# handle_resume — REQ-004
# ============================================================================


async def test_handle_resume_by_thread_id_switches_active(
    fake_evolution: _FakeEvolution,
    monkeypatch: Any,
) -> None:
    """Unit-9: `/resume <T>` (arg contém `-`, heurística de UUID) torna T ativa."""
    # Ownership check: T existe para o número.
    list_mock = MagicMock(
        return_value=[{"thread_id": "abc-1234", "title": None, "active": False}]
    )
    monkeypatch.setattr(commands, "list_threads_for_number", list_mock)
    set_active_mock = MagicMock(return_value=True)
    monkeypatch.setattr(commands, "set_active_thread", set_active_mock)

    await commands.handle_resume("5511999990000", "abc-1234", "inst-1")

    list_mock.assert_called_once_with("5511999990000")
    set_active_mock.assert_called_once_with("5511999990000", "abc-1234")
    assert len(fake_evolution.sent) == 1
    _, _, text = fake_evolution.sent[0]
    assert "abc-1234" in text


async def test_handle_resume_by_title_switches_active(
    fake_evolution: _FakeEvolution,
    monkeypatch: Any,
) -> None:
    """Unit-10: `/resume pagamentos` (arg sem `-`) — get_thread_by_title + set_active."""
    get_by_title_mock = MagicMock(
        return_value={"thread_id": "thread-7", "title": "pagamentos", "active": False}
    )
    monkeypatch.setattr(commands, "get_thread_by_title", get_by_title_mock)
    set_active_mock = MagicMock(return_value=True)
    monkeypatch.setattr(commands, "set_active_thread", set_active_mock)
    # list_threads_for_number NÃO deve ser chamado (caminho por título).
    list_mock = MagicMock(return_value=[])
    monkeypatch.setattr(commands, "list_threads_for_number", list_mock)

    await commands.handle_resume("5511999990000", "pagamentos", "inst-1")

    get_by_title_mock.assert_called_once_with("5511999990000", "pagamentos")
    set_active_mock.assert_called_once_with("5511999990000", "thread-7")
    list_mock.assert_not_called()
    assert len(fake_evolution.sent) == 1
    _, _, text = fake_evolution.sent[0]
    assert "pagamentos" in text


async def test_handle_resume_by_thread_id_rejects_thread_from_other_number(
    fake_evolution: _FakeEvolution,
    monkeypatch: Any,
) -> None:
    """Unit-11: `/resume <T>` quando T pertence a outro número — rejeita sem vazar dono."""
    # Ownership check: T NÃO está em whatsapp_threads para este phone_number.
    list_mock = MagicMock(return_value=[])
    monkeypatch.setattr(commands, "list_threads_for_number", list_mock)
    set_active_mock = MagicMock(return_value=True)
    monkeypatch.setattr(commands, "set_active_thread", set_active_mock)

    await commands.handle_resume("5511999990000", "abc-1234", "inst-1")

    set_active_mock.assert_not_called()
    assert len(fake_evolution.sent) == 1
    _, _, text = fake_evolution.sent[0]
    # Mensagem de rejeição clara, sem vazar "pertence ao número X".
    assert "abc-1234" not in text
    assert "pertenc" not in text.lower() and "dono" not in text.lower()


async def test_handle_resume_without_argument_responds_with_current_active(
    fake_evolution: _FakeEvolution,
    monkeypatch: Any,
) -> None:
    """Unit-12: `/resume` (sem args) responde com id + título da thread ativa."""
    get_active_mock = MagicMock(return_value="thread-current")
    monkeypatch.setattr(commands, "get_or_create_thread_id", get_active_mock)
    list_mock = MagicMock(
        return_value=[
            {"thread_id": "thread-current", "title": "pagamentos", "active": True}
        ]
    )
    monkeypatch.setattr(commands, "list_threads_for_number", list_mock)
    set_active_mock = MagicMock(return_value=True)
    monkeypatch.setattr(commands, "set_active_thread", set_active_mock)

    await commands.handle_resume("5511999990000", "", "inst-1")

    get_active_mock.assert_called_once_with("5511999990000")
    set_active_mock.assert_not_called()
    assert len(fake_evolution.sent) == 1
    _, _, text = fake_evolution.sent[0]
    assert "thread-current" in text
    assert "pagamentos" in text


# ============================================================================
# handle_sessions — REQ-005
# ============================================================================


async def test_handle_sessions_lists_threads_marking_active(
    fake_evolution: _FakeEvolution,
    monkeypatch: Any,
) -> None:
    """Unit-13: `/sessions` lista todas as threads do número, marcando a ativa."""
    list_mock = MagicMock(
        return_value=[
            {"thread_id": "T1", "title": "pagamentos", "active": False},
            {"thread_id": "T2", "title": None, "active": True},
            {"thread_id": "T3", "title": "compras", "active": False},
        ]
    )
    monkeypatch.setattr(commands, "list_threads_for_number", list_mock)

    await commands.handle_sessions("5511999990000", "", "inst-1")

    list_mock.assert_called_once_with("5511999990000")
    assert len(fake_evolution.sent) == 1
    _, _, text = fake_evolution.sent[0]
    # Todos os ids aparecem na listagem.
    assert "T1" in text and "T2" in text and "T3" in text
    # A thread ativa é marcada visualmente (asterisco) e os títulos ausentes
    # caem no placeholder.
    assert "<sem título>" in text
    # O marcador `* ` distingue a ativa das demais.
    lines = text.splitlines()
    active_line = next((line for line in lines if "T2" in line), "")
    assert active_line.lstrip().startswith("*")


async def test_handle_sessions_when_empty_suggests_new(
    fake_evolution: _FakeEvolution,
    monkeypatch: Any,
) -> None:
    """Unit-14: `/sessions` com 0 threads — mensagem orientando `/new`."""
    list_mock = MagicMock(return_value=[])
    monkeypatch.setattr(commands, "list_threads_for_number", list_mock)

    await commands.handle_sessions("5511999990000", "", "inst-1")

    list_mock.assert_called_once_with("5511999990000")
    assert len(fake_evolution.sent) == 1
    _, _, text = fake_evolution.sent[0]
    assert "/new" in text or "new" in text
