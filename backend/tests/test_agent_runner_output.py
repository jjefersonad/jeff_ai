"""Testes do campo aditivo `AgentRunResult.output` (task `unify-message-delivery-pipeline-task-foundation-4`).

Verifica:
- REQ-003 (agent-runner): `AgentRunOutcome` é frozen com `text`/`attachments`.
- REQ-002 (agent-runner): `AgentRunResult.output` é o último campo, default `None`.
- REQ-005 (agent-runner): callers existentes que só leem `status` continuam passando sem mudança.
"""
from __future__ import annotations

import dataclasses

import pytest

from src.application.ports.agent_runner import AgentRunOutcome, AgentRunResult
from src.domain.channels import OutputAttachment


def test_agent_run_outcome_constructs_with_text_and_attachments() -> None:
    outcome = AgentRunOutcome(text="Olá!", attachments=())

    assert outcome.text == "Olá!"
    assert outcome.attachments == ()


def test_agent_run_outcome_is_frozen() -> None:
    outcome = AgentRunOutcome(text="Olá!", attachments=())

    with pytest.raises(dataclasses.FrozenInstanceError):
        outcome.text = "outro"  # type: ignore[misc]


def test_agent_run_outcome_accepts_multimodal_only() -> None:
    attachment = OutputAttachment(path="outputs/foo.png", mime="image/png", display_name="foo.png")

    outcome = AgentRunOutcome(text=None, attachments=(attachment,))

    assert outcome.text is None
    assert outcome.attachments == (attachment,)


def test_agent_run_result_output_defaults_to_none_for_existing_call_sites() -> None:
    # Mesma forma de construção que todo caller pré-existente usa hoje —
    # sem passar `output` (campo não existia antes desta task).
    result = AgentRunResult(thread_id="t1", status="ok")

    assert result.output is None


def test_agent_run_result_output_can_be_set() -> None:
    outcome = AgentRunOutcome(text="Olá!", attachments=())

    result = AgentRunResult(thread_id="t1", status="ok", output=outcome)

    assert result.output is outcome


def test_existing_caller_reading_only_status_is_unaffected() -> None:
    """Regressão explícita para REQ-005: um caller que só lê `status` (padrão de
    `RunScheduledTask` hoje) não precisa saber que `output` existe."""
    result = AgentRunResult(thread_id="t1", status="error", error="boom")

    assert result.status == "error"
