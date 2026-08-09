"""Testes do use case `HandleChatMessage`.

Puro: usa fakes das portas. Cobre:
- REQ-001/REQ-002 (task `usecase-1`): happy path — entrega texto/multimodal
  mesmo sem tool-call de entrega.
- REQ-003 (task `usecase-2`): falhas do agente viram `kind="failure"`;
  `status="ok"` com `output is None` NÃO entrega.
- REQ-004 (task `usecase-3`): `status="interrupted"` reenvia `interrupt`
  ao canal com `kind="interruption"`.
- REQ-005/REQ-006 (task `usecase-4`): identidade propagada sem alteração;
  `deliver` exatamente uma vez por turno com attachments agregados.
- typing-indicator-chat-channels-task-orchestration-1: start/`finally` stop
  em torno do run; sem typing em `precomputed_output`; sem tool de typing.
"""
from __future__ import annotations

import logging
from typing import Any

import pytest

from src.application.ports.agent_runner import (
    AgentRunnerPort,
    AgentRunOutcome,
    AgentRunResult,
    InterruptInfo,
)
from src.application.ports.chat_channel import ChatChannelPort
from src.application.use_cases.handle_chat_message import HandleChatMessage
from src.domain.channels import ChannelKind, OutputAttachment
from src.domain.scheduling import ToolScope
import src.infrastructure.usage.user_key as user_key_mod

# ---------------------------------------------------------------------------
# Fakes locais
# ---------------------------------------------------------------------------


class _RecordingChannel(ChatChannelPort):
    def __init__(
        self,
        *,
        events: list[str] | None = None,
        channel_kind: ChannelKind = ChannelKind.TELEGRAM,
    ) -> None:
        self.calls: list[dict] = []
        self.events: list[str] = events if events is not None else []
        self._channel_kind = channel_kind

    @property
    def channel_kind(self) -> ChannelKind:
        return self._channel_kind

    async def deliver(
        self,
        *,
        user_key: str,
        text: str | None,
        attachments: tuple[OutputAttachment, ...],
        kind: str,
        interrupt: object | None = None,
        thread_id: str | None = None,
    ) -> None:
        self.events.append(f"deliver:{kind}")
        self.calls.append(
            {
                "user_key": user_key,
                "text": text,
                "attachments": attachments,
                "kind": kind,
                "interrupt": interrupt,
                "thread_id": thread_id,
            }
        )

    async def start_typing_indicator(self, *, user_key: str) -> None:
        self.events.append(f"start_typing:{user_key}")

    async def stop_typing_indicator(self, *, user_key: str) -> None:
        self.events.append(f"stop_typing:{user_key}")


class _RecordingRunner(AgentRunnerPort):
    """Registra os kwargs recebidos e devolve `result` (ou levanta `raises`)."""

    def __init__(
        self,
        *,
        result: AgentRunResult | None = None,
        raises: Exception | None = None,
        events: list[str] | None = None,
    ) -> None:
        self._result = result
        self._raises = raises
        self._events = events
        self.calls: list[dict] = []

    async def run(
        self,
        *,
        thread_id: str,
        prompt: str,
        skills: tuple[str, ...],
        tool_scope: ToolScope,
        user_key: str | None = None,
    ) -> AgentRunResult:
        if self._events is not None:
            self._events.append("run")
        self.calls.append(
            {
                "thread_id": thread_id,
                "prompt": prompt,
                "skills": skills,
                "tool_scope": tool_scope,
                "user_key": user_key,
            }
        )
        if self._raises is not None:
            raise self._raises
        assert self._result is not None
        return self._result

    async def resume(
        self,
        *,
        thread_id: str,
        decisions: tuple[dict, ...],
        user_key: str | None = None,
    ) -> AgentRunResult:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# REQ-002 — captura automática do output do agente (happy path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_delivers_text_only_output_without_delivery_tool_call():
    channel = _RecordingChannel()
    runner = _RecordingRunner(
        result=AgentRunResult(
            thread_id="th-1",
            status="ok",
            output=AgentRunOutcome(text="Olá! Sou o Jeff AI...", attachments=()),
        )
    )
    use_case = HandleChatMessage(agent_runner=runner)

    await use_case.execute(channel=channel, user_key="telegram:123", thread_id="th-1", text="oi")

    assert channel.calls == [
        {
            "user_key": "telegram:123",
            "text": "Olá! Sou o Jeff AI...",
            "attachments": (),
            "kind": "normal",
            "interrupt": None,
            "thread_id": None,
        }
    ]


@pytest.mark.asyncio
async def test_execute_delivers_multimodal_only_output_with_text_none():
    attachment = OutputAttachment(path="outputs/foo.docx", mime="application/vnd.openxmlformats", display_name="foo.docx")
    channel = _RecordingChannel()
    runner = _RecordingRunner(
        result=AgentRunResult(
            thread_id="th-1",
            status="ok",
            output=AgentRunOutcome(text=None, attachments=(attachment,)),
        )
    )
    use_case = HandleChatMessage(agent_runner=runner)

    await use_case.execute(channel=channel, user_key="telegram:123", thread_id="th-1", text="gera o documento")

    assert channel.calls == [
        {
            "user_key": "telegram:123",
            "text": None,
            "attachments": (attachment,),
            "kind": "normal",
            "interrupt": None,
            "thread_id": None,
        }
    ]


# ---------------------------------------------------------------------------
# REQ-003 — tratamento uniforme de falha (task usecase-2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_swallows_runner_exception_and_delivers_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    channel = _RecordingChannel()
    runner = _RecordingRunner(raises=RuntimeError("Ollama timeout"))
    use_case = HandleChatMessage(agent_runner=runner)

    with caplog.at_level(logging.ERROR):
        await use_case.execute(
            channel=channel, user_key="telegram:123", thread_id="th-1", text="oi"
        )

    assert channel.calls == [
        {
            "user_key": "telegram:123",
            "text": None,
            "attachments": (),
            "kind": "failure",
            "interrupt": None,
            "thread_id": None,
        }
    ]
    assert any("agent_run_failed" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_execute_delivers_failure_when_status_is_error() -> None:
    channel = _RecordingChannel()
    runner = _RecordingRunner(
        result=AgentRunResult(thread_id="th-1", status="error", error="timeout")
    )
    use_case = HandleChatMessage(agent_runner=runner)

    await use_case.execute(
        channel=channel, user_key="telegram:123", thread_id="th-1", text="oi"
    )

    assert channel.calls == [
        {
            "user_key": "telegram:123",
            "text": None,
            "attachments": (),
            "kind": "failure",
            "interrupt": None,
            "thread_id": None,
        }
    ]


@pytest.mark.asyncio
async def test_execute_output_missing_logs_warning_and_does_not_deliver(
    caplog: pytest.LogCaptureFixture,
) -> None:
    channel = _RecordingChannel()
    runner = _RecordingRunner(
        result=AgentRunResult(thread_id="th-1", status="ok", output=None)
    )
    use_case = HandleChatMessage(agent_runner=runner)

    with caplog.at_level(logging.WARNING):
        await use_case.execute(
            channel=channel, user_key="telegram:123", thread_id="th-1", text="oi"
        )

    assert channel.calls == []
    assert any("agent_output_missing" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# REQ-004 — tratamento de interrupt (task usecase-3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_forwards_interrupt_to_channel_unmodified() -> None:
    interrupt = InterruptInfo(
        action_requests=({"name": "edit_file", "args": {"path": "a.py"}},),
        review_configs=({"allowed_decisions": ["approve", "reject"]},),
    )
    channel = _RecordingChannel()
    runner = _RecordingRunner(
        result=AgentRunResult(
            thread_id="th-1",
            status="interrupted",
            interrupt=interrupt,
        )
    )
    use_case = HandleChatMessage(agent_runner=runner)

    await use_case.execute(
        channel=channel, user_key="telegram:123", thread_id="th-1", text="edita a.py"
    )

    assert len(channel.calls) == 1
    call = channel.calls[0]
    assert call["kind"] == "interruption"
    assert call["text"] is None
    assert call["attachments"] == ()
    assert call["user_key"] == "telegram:123"
    assert call["interrupt"] is interrupt


# ---------------------------------------------------------------------------
# REQ-005 / REQ-006 — identidade + deliver único (task usecase-4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_propagates_identity_without_deriving_channel_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel = _RecordingChannel()
    runner = _RecordingRunner(
        result=AgentRunResult(
            thread_id="abc-def",
            status="ok",
            output=AgentRunOutcome(text="oi", attachments=()),
        )
    )
    use_case = HandleChatMessage(agent_runner=runner)

    from_user_key_calls: list[Any] = []

    def _spy_from_user_key(user_key: str | None) -> ChannelKind | None:
        from_user_key_calls.append(user_key)
        return None

    # O helper real vive em infrastructure; ChannelKind.from_user_key não existe
    # como método — spy nos dois caminhos possíveis de derivação indevida.
    monkeypatch.setattr(user_key_mod, "from_user_key", _spy_from_user_key)
    monkeypatch.setattr(
        ChannelKind,
        "from_user_key",
        classmethod(lambda cls, uk: from_user_key_calls.append(uk) or None),
        raising=False,
    )

    await use_case.execute(
        channel=channel,
        user_key="telegram:123",
        thread_id="abc-def",
        text="oi",
    )

    assert runner.calls == [
        {
            "thread_id": "abc-def",
            "prompt": "oi",
            "skills": (),
            "tool_scope": ToolScope.RESTRICTED,
            "user_key": "telegram:123",
        }
    ]
    assert from_user_key_calls == []


@pytest.mark.asyncio
async def test_execute_delivers_exactly_once_with_aggregated_attachments() -> None:
    attachments = (
        OutputAttachment(path="outputs/a.png", mime="image/png", display_name="a.png"),
        OutputAttachment(
            path="outputs/b.docx",
            mime="application/vnd.openxmlformats",
            display_name="b.docx",
        ),
    )
    channel = _RecordingChannel()
    runner = _RecordingRunner(
        result=AgentRunResult(
            thread_id="th-1",
            status="ok",
            output=AgentRunOutcome(text="pronto", attachments=attachments),
        )
    )
    use_case = HandleChatMessage(agent_runner=runner)

    await use_case.execute(
        channel=channel, user_key="telegram:123", thread_id="th-1", text="gera os dois"
    )

    assert len(channel.calls) == 1
    assert channel.calls[0]["attachments"] == attachments
    assert channel.calls[0]["text"] == "pronto"
    assert channel.calls[0]["kind"] == "normal"


# ---------------------------------------------------------------------------
# typing-indicator-chat-channels-task-orchestration-1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_starts_typing_before_run_and_stops_in_finally() -> None:
    """Unit-1: happy path tipa e para (REQ-001 orchestration)."""
    events: list[str] = []
    channel = _RecordingChannel(events=events)
    runner = _RecordingRunner(
        result=AgentRunResult(
            thread_id="th-1",
            status="ok",
            output=AgentRunOutcome(text="ok", attachments=()),
        ),
        events=events,
    )
    use_case = HandleChatMessage(agent_runner=runner)

    await use_case.execute(
        channel=channel, user_key="telegram:123", thread_id="th-1", text="oi"
    )

    assert events[:3] == [
        "start_typing:telegram:123",
        "run",
        "stop_typing:telegram:123",
    ]
    assert events.count("start_typing:telegram:123") == 1
    assert events.count("stop_typing:telegram:123") == 1


@pytest.mark.asyncio
async def test_execute_stops_typing_when_runner_raises() -> None:
    """Unit-2a: falha do agente ainda para o typing (REQ-001)."""
    events: list[str] = []
    channel = _RecordingChannel(events=events)
    runner = _RecordingRunner(raises=RuntimeError("boom"), events=events)
    use_case = HandleChatMessage(agent_runner=runner)

    await use_case.execute(
        channel=channel, user_key="telegram:123", thread_id="th-1", text="oi"
    )

    assert "start_typing:telegram:123" in events
    assert "run" in events
    assert "stop_typing:telegram:123" in events
    assert events.index("stop_typing:telegram:123") > events.index("run")
    assert channel.calls == [
        {
            "user_key": "telegram:123",
            "text": None,
            "attachments": (),
            "kind": "failure",
            "interrupt": None,
            "thread_id": None,
        }
    ]


@pytest.mark.asyncio
async def test_execute_stops_typing_when_interrupted() -> None:
    """Unit-2b: interrupção HITL ainda para o typing (REQ-001)."""
    interrupt = InterruptInfo(
        action_requests=({"name": "edit_file", "args": {"path": "a.py"}},),
        review_configs=({"allowed_decisions": ["approve", "reject"]},),
    )
    events: list[str] = []
    channel = _RecordingChannel(events=events)
    runner = _RecordingRunner(
        result=AgentRunResult(
            thread_id="th-1",
            status="interrupted",
            interrupt=interrupt,
        ),
        events=events,
    )
    use_case = HandleChatMessage(agent_runner=runner)

    await use_case.execute(
        channel=channel, user_key="telegram:123", thread_id="th-1", text="edita"
    )

    assert events.index("stop_typing:telegram:123") > events.index("run")
    assert events.index("deliver:interruption") > events.index("stop_typing:telegram:123")
    assert channel.calls[0]["kind"] == "interruption"
    assert channel.calls[0]["interrupt"] is interrupt


@pytest.mark.asyncio
async def test_execute_precomputed_output_does_not_type() -> None:
    """Unit-3: notify agendado não tipa (REQ-002)."""
    events: list[str] = []
    channel = _RecordingChannel(events=events)
    runner = _RecordingRunner(
        result=AgentRunResult(
            thread_id="th-1",
            status="ok",
            output=AgentRunOutcome(text="unused", attachments=()),
        ),
        events=events,
    )
    use_case = HandleChatMessage(agent_runner=runner)

    await use_case.execute(
        channel=channel,
        user_key="telegram:123",
        thread_id="th-1",
        text="ignored",
        precomputed_output=AgentRunOutcome(text="pré", attachments=()),
    )

    assert runner.calls == []
    assert not any(e.startswith("start_typing:") or e.startswith("stop_typing:") for e in events)
    assert channel.calls == [
        {
            "user_key": "telegram:123",
            "text": "pré",
            "attachments": (),
            "kind": "normal",
            "interrupt": None,
            "thread_id": None,
        }
    ]


@pytest.mark.asyncio
async def test_execute_web_channel_is_excluded_by_orchestrator() -> None:
    """Unit-5: orquestrador não chama typing para WEB (REQ-002/REQ-006) — não
    basta o no-op do adapter, o port não pode nem ser invocado."""
    events: list[str] = []
    channel = _RecordingChannel(events=events, channel_kind=ChannelKind.WEB)
    runner = _RecordingRunner(
        result=AgentRunResult(
            thread_id="th-1",
            status="ok",
            output=AgentRunOutcome(text="ok", attachments=()),
        ),
        events=events,
    )
    use_case = HandleChatMessage(agent_runner=runner)

    await use_case.execute(
        channel=channel, user_key="web:user-7", thread_id="th-1", text="oi"
    )

    assert not any(
        e.startswith("start_typing:") or e.startswith("stop_typing:") for e in events
    )


@pytest.mark.asyncio
async def test_execute_scheduled_channel_is_excluded_by_orchestrator() -> None:
    """Unit-5b: mesmo comportamento para SCHEDULED (REQ-002/REQ-006)."""
    events: list[str] = []
    channel = _RecordingChannel(events=events, channel_kind=ChannelKind.SCHEDULED)
    runner = _RecordingRunner(
        result=AgentRunResult(
            thread_id="th-1",
            status="ok",
            output=AgentRunOutcome(text="ok", attachments=()),
        ),
        events=events,
    )
    use_case = HandleChatMessage(agent_runner=runner)

    await use_case.execute(
        channel=channel, user_key="telegram:123", thread_id="th-1", text="oi"
    )

    assert not any(
        e.startswith("start_typing:") or e.startswith("stop_typing:") for e in events
    )


@pytest.mark.asyncio
async def test_execute_typing_disabled_via_env_flag(monkeypatch) -> None:
    """Unit-6: `TYPING_INDICATOR_ENABLED=false` desliga start/stop (REQ-003)."""
    monkeypatch.setenv("TYPING_INDICATOR_ENABLED", "false")
    events: list[str] = []
    channel = _RecordingChannel(events=events)
    runner = _RecordingRunner(
        result=AgentRunResult(
            thread_id="th-1",
            status="ok",
            output=AgentRunOutcome(text="ok", attachments=()),
        ),
        events=events,
    )
    use_case = HandleChatMessage(agent_runner=runner)

    await use_case.execute(
        channel=channel, user_key="telegram:123", thread_id="th-1", text="oi"
    )

    assert not any(
        e.startswith("start_typing:") or e.startswith("stop_typing:") for e in events
    )
    assert "run" in events


def test_unified_tool_set_has_no_typing_tools() -> None:
    """Unit-4: ausência no registry de tools (REQ-003)."""
    from src.agents.unified.agent import _TOOL_NAMES
    from src.agents.unified.effects import TOOL_EFFECTS

    typing_names = {
        n
        for n in (*_TOOL_NAMES, *TOOL_EFFECTS)
        if "typing" in n.lower() or n.lower() in {"start_typing", "stop_typing"}
    }
    assert typing_names == set()
