"""Hook pós-resume HITL → `CompleteScheduledTaskAfterResume`.

Chamado pelos adapters Telegram/WhatsApp após `agent_runner.resume`.
Best-effort: falha de scheduling NÃO derruba o handler do canal.
"""
from __future__ import annotations

import logging
from typing import Any

from src.application.ports.agent_runner import AgentRunResult

logger = logging.getLogger(__name__)


async def maybe_complete_scheduled_task_after_resume(
    *,
    thread_id: str,
    decision_type: str,
    result: AgentRunResult | None,
) -> None:
    """Fecha tarefa `WAITING_HUMAN` da `thread_id` conforme o outcome do resume.

    - `reject` (ou resume `None`/erro) → failed
    - `approve` + `status=ok` → succeeded
    - `status=interrupted` de novo → no-op (continua WAITING_HUMAN)
    - sem tarefa WAITING_HUMAN → no-op no use case
    """
    if result is not None and result.status == "interrupted":
        return

    if decision_type == "reject" or result is None:
        outcome: str = "failed"
        error = (
            "resume falhou"
            if result is None
            else (result.error or "Interrupção rejeitada pelo usuário.")
        )
    elif result.status == "ok":
        outcome = "succeeded"
        error = None
    else:
        outcome = "failed"
        error = result.error or f"Agente retornou status={result.status!r}."

    try:
        from src.composition.dependencies import (
            build_complete_scheduled_task_after_resume,
        )

        await build_complete_scheduled_task_after_resume().execute(
            thread_id=thread_id,
            outcome=outcome,  # type: ignore[arg-type]
            error=error,
        )
    except Exception:  # noqa: BLE001 — fronteira do canal
        logger.exception(
            "complete_scheduled_task_after_resume falhou thread_id=%s "
            "decision=%s result_status=%s",
            thread_id,
            decision_type,
            getattr(result, "status", None),
        )


def decision_type_from_decisions(decisions: tuple[dict[str, Any], ...]) -> str:
    """Extrai o tipo da primeira decisão (`approve`/`reject`/…)."""
    if not decisions:
        return "reject"
    raw = decisions[0].get("type", "reject")
    return str(raw) if raw else "reject"
