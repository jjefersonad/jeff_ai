"""Testes do estado de aprovação pendente do WhatsApp (`src/infrastructure/whatsapp/approval.py`).

Cobre a task `whatsapp-tool-approval-task-foundation-1`:

- REQ-008 (`-unit-1`): registrar uma `PendingApproval` a torna recuperável pelo
  mesmo `phone_number`, com `awaiting_edit_text` default `False`.
- REQ-008 (`-unit-2`): `clear_pending_approval` remove a entrada — lookup
  subsequente não encontra nada.
"""

from __future__ import annotations

from src.infrastructure.whatsapp import approval


def test_set_pending_approval_makes_it_retrievable_by_phone_number() -> None:
    """Unit-1: registrar uma PendingApproval a torna recuperável pelo mesmo phone_number."""
    phone = "5511999998888"
    pending = approval.PendingApproval(
        thread_id="thread-abc",
        action_requests=({"name": "edit_file", "args": {}},),
        review_configs=({"allowed_decisions": ["approve", "reject"]},),
    )

    approval.set_pending_approval(phone, pending)

    retrieved = approval.get_pending_approval(phone)
    assert retrieved is pending
    assert retrieved.awaiting_edit_text is False

    approval.clear_pending_approval(phone)


def test_clear_pending_approval_removes_the_entry() -> None:
    """Unit-2: pop remove a entrada — lookup subsequente não encontra nada."""
    phone = "5511999997777"
    pending = approval.PendingApproval(
        thread_id="thread-xyz",
        action_requests=({"name": "git_commit", "args": {}},),
        review_configs=({"allowed_decisions": ["approve", "reject"]},),
    )
    approval.set_pending_approval(phone, pending)
    assert approval.get_pending_approval(phone) is not None

    approval.clear_pending_approval(phone)

    assert approval.get_pending_approval(phone) is None


def test_clear_pending_approval_is_idempotent_for_unknown_phone() -> None:
    """clear_pending_approval não deve levantar erro para phone_number sem pendência."""
    approval.clear_pending_approval("5511900000000-does-not-exist")
