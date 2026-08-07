"""Testes do domínio de scheduling (task `agendamento-jeff-cli-task-domain-1`).

Puro: sem framework, sem I/O. Cobre:
- Máquina de estado de `ScheduledTask` (transições válidas/inválidas — REQ-002).
- Campo `tool_scope` tipado como `ToolScope` (REQ-006).
- Validação de `Schedule.__post_init__` para `kind="cron"` e `"once"`.
- Ausência de imports proibidos (langgraph / psycopg / fastapi / apscheduler).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.domain.scheduling.scheduled_task import (
    NOTIFY_SKIP_DELIVERY_USER_KEY_MISSING,
    NOTIFY_SKIP_OUTPUT_MISSING,
    Schedule,
    ScheduledTask,
    TaskStatus,
    ToolScope,
)
from src.domain.shared.errors import DomainError

# ---------------------------------------------------------------------------
# REQ-002 — Máquina de estado
# ---------------------------------------------------------------------------


def _new_task() -> ScheduledTask:
    """Constrói uma tarefa no estado SCHEDULED para uso nos testes."""
    return ScheduledTask(
        id="t-1",
        prompt="olá",
        thread_id="th-1",
        schedule=Schedule(kind="once", expr="2026-01-01T00:00:00"),
        tool_scope=ToolScope.RESTRICTED,
    )


def test_task_starts_in_scheduled_state():
    t = _new_task()
    assert t.status == TaskStatus.SCHEDULED


def test_start_transitions_scheduled_to_running():
    t = _new_task()
    t.start()
    assert t.status == TaskStatus.RUNNING
    assert t.started_at is not None


def test_succeed_transitions_running_to_succeeded():
    t = _new_task()
    t.start()
    t.succeed()
    assert t.status == TaskStatus.SUCCEEDED
    assert t.finished_at is not None


def test_fail_transitions_running_to_failed_with_error():
    t = _new_task()
    t.start()
    t.fail("boom")
    assert t.status == TaskStatus.FAILED
    assert t.finished_at is not None
    assert t.error == "boom"


def test_succeed_outside_running_is_rejected():
    t = _new_task()  # ainda SCHEDULED
    with pytest.raises(DomainError, match="RUNNING"):
        t.succeed()


def test_fail_outside_running_is_rejected():
    t = _new_task()
    with pytest.raises(DomainError, match="RUNNING"):
        t.fail("nunca rodou")


def test_start_from_running_is_rejected():
    t = _new_task()
    t.start()
    with pytest.raises(DomainError, match="SCHEDULED"):
        t.start()


def test_start_from_terminal_state_is_rejected():
    t = _new_task()
    t.start()
    t.succeed()
    with pytest.raises(DomainError, match="SCHEDULED"):
        t.start()


def test_succeed_from_succeeded_is_rejected():
    t = _new_task()
    t.start()
    t.succeed()
    with pytest.raises(DomainError, match="RUNNING"):
        t.succeed()


# ---------------------------------------------------------------------------
# scheduled-channel-routines — delivery_user_key / WAITING_HUMAN / rearm
# ---------------------------------------------------------------------------


def test_delivery_user_key_optional_and_effective_destination():
    """REQ-001 targeting: optional delivery; effective falls back to owner."""
    with_delivery = ScheduledTask(
        id="t-d1",
        prompt="olá",
        thread_id="th-1",
        schedule=Schedule(kind="once", expr="2026-01-01T00:00:00"),
        owner_user_key="web:1",
        delivery_user_key="whatsapp:5511",
    )
    without_delivery = ScheduledTask(
        id="t-d2",
        prompt="olá",
        thread_id="th-2",
        schedule=Schedule(kind="once", expr="2026-01-01T00:00:00"),
        owner_user_key="web:1",
    )
    assert with_delivery.delivery_user_key == "whatsapp:5511"
    assert with_delivery.effective_delivery_user_key == "whatsapp:5511"
    assert without_delivery.delivery_user_key is None
    assert without_delivery.effective_delivery_user_key == "web:1"


# ---------------------------------------------------------------------------
# fix-scheduled-whatsapp-delivery — notify_status / notify_error
# ---------------------------------------------------------------------------


def test_mark_notify_delivered_sets_status_without_touching_execution():
    """REQ-002 observability: delivered; execução intacta."""
    t = _new_task()
    t.start()
    t.succeed()
    assert t.notify_status is None
    assert t.notify_error is None

    t.mark_notify_delivered()

    assert t.notify_status == "delivered"
    assert t.notify_error is None
    assert t.status == TaskStatus.SUCCEEDED
    assert t.error is None


def test_mark_notify_skipped_with_canonical_reason():
    """REQ-002: skipped + motivo canônico `output_missing`."""
    t = _new_task()
    t.start()
    t.succeed()
    t.mark_notify_skipped(NOTIFY_SKIP_OUTPUT_MISSING)

    assert t.notify_status == "skipped"
    assert t.notify_error == "output_missing"
    assert t.status == TaskStatus.SUCCEEDED


def test_mark_notify_failed_preserves_execution_status():
    """REQ-002: failed + mensagem; status/error de execução intactos."""
    t = _new_task()
    t.start()
    t.succeed()
    t.mark_notify_failed("canal whatsapp não registrado")

    assert t.notify_status == "failed"
    assert t.notify_error == "canal whatsapp não registrado"
    assert t.status == TaskStatus.SUCCEEDED
    assert t.error is None


def test_notify_skip_canonical_reasons_exported():
    """Motivos canônicos estáveis para API/tests."""
    assert NOTIFY_SKIP_OUTPUT_MISSING == "output_missing"
    assert NOTIFY_SKIP_DELIVERY_USER_KEY_MISSING == "delivery_user_key_missing"


def test_waiting_human_from_running_only():
    """REQ-001 human-intervention: RUNNING → WAITING_HUMAN; else DomainError."""
    t = _new_task()
    t.start()
    t.waiting_human()
    assert t.status == TaskStatus.WAITING_HUMAN

    again = _new_task()
    with pytest.raises(DomainError, match="RUNNING"):
        again.waiting_human()


def test_resume_succeed_and_fail_from_waiting_human_only():
    """resume-1: WAITING_HUMAN → SUCCEEDED/FAILED; outros estados rejeitam."""
    ok = _new_task()
    ok.start()
    ok.waiting_human()
    ok.resume_succeed()
    assert ok.status == TaskStatus.SUCCEEDED

    fail = _new_task()
    fail.start()
    fail.waiting_human()
    fail.resume_fail("reject")
    assert fail.status == TaskStatus.FAILED
    assert fail.error == "reject"

    not_waiting = _new_task()
    not_waiting.start()
    with pytest.raises(DomainError, match="WAITING_HUMAN"):
        not_waiting.resume_succeed()
    with pytest.raises(DomainError, match="WAITING_HUMAN"):
        not_waiting.resume_fail("x")


def test_rearm_for_cron_from_terminal_states():
    """Decision 5: cron SUCCEEDED/FAILED → SCHEDULED; once rejects."""
    cron = ScheduledTask(
        id="t-cron",
        prompt="olá",
        thread_id="th-cron",
        schedule=Schedule(kind="cron", expr="0 9 * * *"),
    )
    cron.start()
    cron.succeed()
    cron.rearm_for_cron()
    assert cron.status == TaskStatus.SCHEDULED
    cron.start()  # elegível de novo
    assert cron.status == TaskStatus.RUNNING

    cron_fail = ScheduledTask(
        id="t-cron-f",
        prompt="olá",
        thread_id="th-cron-f",
        schedule=Schedule(kind="cron", expr="0 9 * * *"),
    )
    cron_fail.start()
    cron_fail.fail("x")
    cron_fail.rearm_for_cron()
    assert cron_fail.status == TaskStatus.SCHEDULED

    once = _new_task()
    once.start()
    once.succeed()
    with pytest.raises(DomainError, match="cron"):
        once.rearm_for_cron()


# ---------------------------------------------------------------------------
# REQ-006 — tool_scope tipado
# ---------------------------------------------------------------------------


def test_tool_scope_is_typed_field_with_default_restricted():
    """Default sensato: RESTRICTED — só promove a FULL se o caller pedir."""
    t = _new_task()
    assert t.tool_scope == ToolScope.RESTRICTED
    assert isinstance(t.tool_scope, ToolScope)


def test_tool_scope_full_is_accepted():
    t = ScheduledTask(
        id="t-2",
        prompt="olá",
        thread_id="th-2",
        schedule=Schedule(kind="once", expr="2026-01-01T00:00:00"),
        tool_scope=ToolScope.FULL,
    )
    assert t.tool_scope == ToolScope.FULL


# ---------------------------------------------------------------------------
# Validação de Schedule
# ---------------------------------------------------------------------------


def test_schedule_once_accepts_iso_datetime():
    s = Schedule(kind="once", expr="2026-12-31T23:59:00")
    assert s.kind == "once"
    assert s.expr == "2026-12-31T23:59:00"


@pytest.mark.parametrize("expr", ["0 9 * * *", "*/15 * * * *", "0 0 1 * *"])
def test_schedule_cron_accepts_valid_5_field_expression(expr: str):
    s = Schedule(kind="cron", expr=expr)
    assert s.kind == "cron"
    assert s.expr == expr


def test_schedule_cron_rejects_too_few_fields():
    with pytest.raises(DomainError, match="cron"):
        Schedule(kind="cron", expr="0 9 * *")


def test_schedule_cron_rejects_out_of_range_hour():
    """Hora 25 está fora do range [0,23] — cinco campos válidos não bastam."""
    with pytest.raises(DomainError, match="cron"):
        Schedule(kind="cron", expr="0 25 * * *")


def test_schedule_cron_rejects_out_of_range_minute():
    """Minuto 60 está fora do range [0,59] — cinco campos válidos não bastam."""
    with pytest.raises(DomainError, match="cron"):
        Schedule(kind="cron", expr="60 9 * * *")


def test_schedule_cron_rejects_non_numeric_field():
    with pytest.raises(DomainError, match="cron"):
        Schedule(kind="cron", expr="x 9 * * *")


def test_schedule_once_rejects_malformed_expr():
    with pytest.raises(DomainError, match="once"):
        Schedule(kind="once", expr="não-é-iso")


def test_schedule_rejects_unknown_kind():
    with pytest.raises(DomainError, match="kind"):
        Schedule(kind="intervalo", expr="x")  # type: ignore[arg-type]


def test_schedule_rejects_empty_expr():
    with pytest.raises(DomainError, match="expr"):
        Schedule(kind="once", expr="")


# ---------------------------------------------------------------------------
# Validação da entidade ScheduledTask
# ---------------------------------------------------------------------------


def test_scheduled_task_requires_non_empty_prompt():
    with pytest.raises(DomainError, match="prompt"):
        ScheduledTask(
            id="t-x",
            prompt="   ",
            thread_id="th-1",
            schedule=Schedule(kind="once", expr="2026-01-01T00:00:00"),
        )


def test_scheduled_task_requires_id():
    with pytest.raises(DomainError, match="id"):
        ScheduledTask(
            id="",
            prompt="p",
            thread_id="th-1",
            schedule=Schedule(kind="once", expr="2026-01-01T00:00:00"),
        )


def test_scheduled_task_requires_thread_id():
    with pytest.raises(DomainError, match="thread_id"):
        ScheduledTask(
            id="t-1",
            prompt="p",
            thread_id="",
            schedule=Schedule(kind="once", expr="2026-01-01T00:00:00"),
        )


def test_scheduled_task_default_timeout_is_sensible():
    t = _new_task()
    assert t.timeout_seconds > 0
    assert t.timeout_seconds <= 24 * 60 * 60  # ≤ 1 dia


def test_scheduled_task_rejects_non_positive_timeout():
    with pytest.raises(DomainError, match="timeout"):
        ScheduledTask(
            id="t-1",
            prompt="p",
            thread_id="th-1",
            schedule=Schedule(kind="once", expr="2026-01-01T00:00:00"),
            timeout_seconds=0,
        )


# ---------------------------------------------------------------------------
# Pureza: zero import proibido
# ---------------------------------------------------------------------------


_FORBIDDEN = ("langgraph", "psycopg", "fastapi", "apscheduler")


def test_domain_module_has_no_framework_imports():
    """domain/ não pode importar nada de framework — só stdlib + domínio."""
    src = (Path(__file__).parent.parent / "src" / "domain" / "scheduling" / "scheduled_task.py").read_text()
    # Remove comentários e docstrings (defesa contra menção explicativa em comentário)
    no_strings = re.sub(r'""".*?"""', "", src, flags=re.DOTALL)
    no_strings = re.sub(r"'''.*?'''", "", no_strings, flags=re.DOTALL)
    for forbidden in _FORBIDDEN:
        # Procura pelo padrão `import X` ou `from X` (não em string de docstring)
        assert not re.search(rf"^\s*(import|from)\s+{forbidden}\b", no_strings, flags=re.MULTILINE), (
            f"domain/scheduling/scheduled_task.py não pode importar '{forbidden}'"
        )
