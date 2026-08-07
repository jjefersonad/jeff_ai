"""Testes da captura de anexos do output do agente em `LangGraphDirectAgentRunner`.

Cobre a task `unify-message-delivery-pipeline-task-capture-2` (spec
`agent-output-capture`):

- REQ-002: cada `ToolMessage` geradora (content JSON com `path`) do turno
  atual vira um `OutputAttachment`, em ordem cronológica; `ToolMessage`s de
  turnos anteriores (antes do último `HumanMessage`) são excluídas.
- REQ-002: múltiplas tools geradoras no mesmo turno → múltiplos anexos, sem dedup.
- REQ-003: `mime`/`display_name` resolvidos pela extensão de `path`, com
  fallback para extensão desconhecida.

Mesmo padrão de mocking de `test_langgraph_direct_runner_output_capture.py`.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.domain.channels import OutputAttachment
from src.domain.scheduling import ToolScope
from src.infrastructure.agent_runtime.langgraph_direct_runner import (
    LangGraphDirectAgentRunner,
)


def _tool_message(*, name: str, path: str, tool_call_id: str) -> ToolMessage:
    return ToolMessage(
        content=json.dumps({"path": path, "url": f"/api/files/{path}"}),
        name=name,
        tool_call_id=tool_call_id,
    )


@asynccontextmanager
async def _fake_pg_context():
    yield MagicMock()


async def _run_with_fake_state(messages: list[Any]):
    fake_graph = MagicMock()
    fake_graph.ainvoke = AsyncMock(return_value={"messages": messages})

    with (
        patch(
            "src.infrastructure.agent_runtime.langgraph_direct_runner"
            ".AsyncPostgresSaver.from_conn_string",
            return_value=_fake_pg_context(),
        ),
        patch(
            "src.infrastructure.agent_runtime.langgraph_direct_runner"
            ".AsyncPostgresStore.from_conn_string",
            return_value=_fake_pg_context(),
        ),
        patch(
            "src.infrastructure.agent_runtime.langgraph_direct_runner.build_unified",
            return_value=fake_graph,
        ),
    ):
        runner = LangGraphDirectAgentRunner(postgres_uri="postgresql://unused")
        return await runner.run(
            thread_id="thread-attach",
            prompt="gere um documento",
            skills=(),
            tool_scope=ToolScope.RESTRICTED,
        )


@pytest.mark.asyncio
async def test_single_generation_tool_message_yields_one_attachment() -> None:
    messages = [
        HumanMessage(content="gere um documento"),
        _tool_message(name="create_docx_document", path="outputs/foo.docx", tool_call_id="call-1"),
        AIMessage(content="Aqui está o documento", tool_calls=[]),
    ]

    result = await _run_with_fake_state(messages)

    assert result.output is not None
    assert result.output.attachments == (
        OutputAttachment(
            path="outputs/foo.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            display_name="foo.docx",
            url="/api/files/outputs/foo.docx",
        ),
    )


@pytest.mark.asyncio
async def test_multiple_generation_tools_same_turn_yield_multiple_attachments_in_order() -> None:
    messages = [
        HumanMessage(content="gere uma imagem e um docx"),
        _tool_message(name="create_image_from_prompt", path="outputs/foo.png", tool_call_id="call-1"),
        _tool_message(name="create_docx_document", path="outputs/bar.docx", tool_call_id="call-2"),
        AIMessage(content="Prontos!", tool_calls=[]),
    ]

    result = await _run_with_fake_state(messages)

    assert result.output is not None
    assert [a.path for a in result.output.attachments] == ["outputs/foo.png", "outputs/bar.docx"]


@pytest.mark.asyncio
async def test_prior_turn_tool_message_is_excluded() -> None:
    messages = [
        # Turno anterior — já respondido, não deve aparecer nesta captura.
        HumanMessage(content="gere um docx"),
        _tool_message(name="create_docx_document", path="outputs/bar.docx", tool_call_id="call-old"),
        AIMessage(content="Pronto!", tool_calls=[]),
        # Turno atual — só este ToolMessage deve virar attachment.
        HumanMessage(content="agora gere uma imagem"),
        _tool_message(name="create_image_from_prompt", path="outputs/foo.png", tool_call_id="call-new"),
        AIMessage(content="Aqui está", tool_calls=[]),
    ]

    result = await _run_with_fake_state(messages)

    assert result.output is not None
    assert [a.path for a in result.output.attachments] == ["outputs/foo.png"]


@pytest.mark.asyncio
async def test_mime_resolution_known_and_unknown_extensions() -> None:
    messages = [
        HumanMessage(content="gere arquivos"),
        _tool_message(name="create_image_from_prompt", path="outputs/foo.png", tool_call_id="call-1"),
        _tool_message(name="save_generated_tool", path="outputs/foo.xyz123", tool_call_id="call-2"),
        AIMessage(content="Prontos!", tool_calls=[]),
    ]

    result = await _run_with_fake_state(messages)

    assert result.output is not None
    known, unknown = result.output.attachments
    assert known.mime == "image/png"
    assert known.display_name == "foo.png"
    assert unknown.mime == "application/octet-stream"
    assert unknown.display_name == "foo.xyz123"


@pytest.mark.asyncio
async def test_create_pdf_document_tool_message_yields_pdf_attachment() -> None:
    """Regressão REQ-004: ToolMessage de create_pdf_document vira anexo application/pdf.

    O capturador é shape-based (sem allowlist por nome de tool) — path `.pdf`
    + url bastam para mime application/pdf.
    """
    messages = [
        HumanMessage(content="gere um pdf"),
        ToolMessage(
            content=json.dumps(
                {
                    "path": "outputs/documents/pdf/x.pdf",
                    "url": "/api/files/pdf/x.pdf",
                    "metadata": {"kind": "pdf"},
                }
            ),
            name="create_pdf_document",
            tool_call_id="call-pdf-1",
        ),
        AIMessage(content="Aqui está o PDF", tool_calls=[]),
    ]

    result = await _run_with_fake_state(messages)

    assert result.output is not None
    assert result.output.attachments == (
        OutputAttachment(
            path="outputs/documents/pdf/x.pdf",
            mime="application/pdf",
            display_name="x.pdf",
            url="/api/files/pdf/x.pdf",
        ),
    )
