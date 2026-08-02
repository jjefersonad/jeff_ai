"""Testes do renderer de aprovação inline (`src/infrastructure/telegram/approval.py`).

Cobre a task `telegram-tool-approval-task-approval-3`:

- REQ-002 cenário "Interrupt com approve+edit+reject"
  (`-unit-1`): para 1 `action_request` com `allowed_decisions` =
  `["approve", "edit", "reject"]`, o teclado tem 3 botões com labels
  "Aprovar"/"Editar"/"Rejeitar".
- REQ-002 cenário "Múltiplos action_requests no mesmo interrupt"
  (`-unit-2`): para mais de 1 `action_request`, "Editar" some do teclado
  e ficam só "Aprovar" + "Rejeitar" (decisão em lote).

O teste `-unit-3` (handler dispatch) está em
`test_telegram_authorization.py` porque cruza a fronteira
`authorization.make_message_handler` → `approval.send_approval_keyboard`.
"""

from __future__ import annotations

from telegram import InlineKeyboardMarkup

from src.application.ports.agent_runner import InterruptInfo
from src.infrastructure.telegram import approval


def _make_interrupt(
    *,
    action_requests: tuple[dict, ...],
    review_configs: tuple[dict, ...],
) -> InterruptInfo:
    return InterruptInfo(
        action_requests=action_requests,
        review_configs=review_configs,
    )


def test_build_keyboard_renders_three_buttons_for_single_item_interrupt() -> None:
    """Unit-1: 1 action_request + allowed_decisions [approve, edit, reject] → 3 botões.

    Verifica REQ-002 cenário "Interrupt com approve+edit+reject".
    """
    interrupt = _make_interrupt(
        action_requests=(
            {"name": "create_image_from_prompt", "args": {"prompt": "gato"}},
        ),
        review_configs=({"allowed_decisions": ["approve", "edit", "reject"]},),
    )

    markup = approval.build_keyboard(interrupt)

    assert isinstance(markup, InlineKeyboardMarkup)
    assert len(markup.inline_keyboard) == 1
    row = markup.inline_keyboard[0]
    assert len(row) == 3
    labels = [btn.text for btn in row]
    assert labels == ["Aprovar", "Editar", "Rejeitar"]
    # Callback data deve ser parseável de volta para a decisão correspondente
    # (usado pela task de callback). Não exigimos a string exata — só que
    # seja não-vazia e mapeie para as 3 decisões esperadas, sem colisão.
    callback_data = [btn.callback_data for btn in row]
    assert all(isinstance(d, str) and d for d in callback_data)
    assert len(set(callback_data)) == 3


def test_build_keyboard_drops_edit_button_when_multiple_action_requests() -> None:
    """Unit-2: 2+ action_requests → só 'Aprovar' + 'Rejeitar', sem 'Editar'.

    Verifica REQ-002 cenário "Múltiplos action_requests no mesmo interrupt"
    — decisão em lote (aprova-todos / rejeita-todos), sem edição
    item-a-item.
    """
    interrupt = _make_interrupt(
        action_requests=(
            {"name": "create_image_from_prompt", "args": {"prompt": "a"}},
            {"name": "create_image_from_prompt", "args": {"prompt": "b"}},
        ),
        review_configs=({"allowed_decisions": ["approve", "edit", "reject"]},),
    )

    markup = approval.build_keyboard(interrupt)

    assert len(markup.inline_keyboard) == 1
    row = markup.inline_keyboard[0]
    labels = [btn.text for btn in row]
    assert labels == ["Aprovar", "Rejeitar"]
    assert "Editar" not in labels
