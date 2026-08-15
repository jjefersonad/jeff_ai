"""Teste de regressão: `build_unified()` sem argumentos preserva o wiring
completo de `create_deep_agent()` (task `agendamento-jeff-cli-task-tests-1`).

Cobre os critérios de aceite:
- Cenário "chamada sem argumentos" do delta
  `agendamento-jeff-cli-unified-agent-graph-spec` ("Checkpointer/store
  injetáveis"): `build_unified()` continua funcionando sem passar
  `checkpointer`/`store`.
- O grafo resultante tem o MESMO conjunto de tools/subagentes/middlewares
  que antes da mudança: a parametrização (task-graph-1) deveria só
  ADICIONAR `checkpointer`/`store` como kwargs opcionais em
  `create_deep_agent(...)` — nada mais nesse call-site deveria ter mudado.

`test_build_unified_parametrization.py` (task-graph-1) já cobre
checkpointer/store isoladamente; este arquivo cobre o resto do call-site
que aquele teste não verifica (`tools`, `subagents`, `system_prompt`,
`interrupt_on`, `middleware`, `backend`).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

from src.agents.unified import agent as agent_module
from src.agents.unified.agent import (
    _SYSTEM_PROMPT,
    _UNIFIED_SUBAGENTS,
    _UNIFIED_TOOLS,
    _interrupt_on,
    build_unified,
)
from src.agents.unified.chat_attachment_preprocessing_middleware import (
    ChatAttachmentPreprocessingMiddleware,
)
from src.agents.unified.envelope_middleware import EnvelopeMiddleware
from src.agents.unified.envelope_proposal import EnvelopeLifecycleMiddleware
from src.agents.unified.mcp_tool_availability import McpToolAvailabilityMiddleware
from src.agents.unified.mcp_tools_middleware import McpToolsMiddleware
from src.agents.unified.role_scoped_tools_middleware import RoleScopedToolsMiddleware
from src.agents.unified.scoped_skills_middleware import ScopedSkillsMiddleware
from src.models.fallback_model import unified_model


class _FakeCompiledGraph:
    """Stand-in para o retorno de `create_deep_agent` — só precisa aceitar
    `.with_config(...)` igual ao `CompiledStateGraph` real do LangGraph."""

    def with_config(self, _config: Any) -> "_FakeCompiledGraph":
        return self


def _call_build_unified_and_capture_kwargs() -> dict[str, Any]:
    with patch.object(
        agent_module, "create_deep_agent", side_effect=lambda **_kwargs: _FakeCompiledGraph()
    ) as spy:
        build_unified()
        return spy.call_args.kwargs


def test_build_unified_without_args_keeps_same_model() -> None:
    kwargs = _call_build_unified_and_capture_kwargs()
    assert kwargs["model"] is unified_model


def test_build_unified_without_args_keeps_same_tools() -> None:
    """A mesma lista `_UNIFIED_TOOLS` do módulo é repassada — a parametrização
    não filtra, reordena nem substitui as tools registradas."""
    kwargs = _call_build_unified_and_capture_kwargs()
    assert kwargs["tools"] is _UNIFIED_TOOLS


def test_build_unified_without_args_keeps_same_subagents() -> None:
    kwargs = _call_build_unified_and_capture_kwargs()
    assert kwargs["subagents"] is _UNIFIED_SUBAGENTS


def test_build_unified_without_args_keeps_same_system_prompt() -> None:
    kwargs = _call_build_unified_and_capture_kwargs()
    assert kwargs["system_prompt"] == _SYSTEM_PROMPT


def test_build_unified_without_args_keeps_same_interrupt_on() -> None:
    kwargs = _call_build_unified_and_capture_kwargs()
    assert kwargs["interrupt_on"] is _interrupt_on


def test_build_unified_without_args_keeps_same_middleware_types_and_order() -> None:
    """`middleware=[...]` ordem canônica (D9 session-file-sandbox):
    EnvelopeLifecycle → McpTools* → RoleScoped → Envelope →
    ChatAttachmentPreprocessing → ScopedSkills.
    """
    kwargs = _call_build_unified_and_capture_kwargs()
    middleware_types = [type(m) for m in kwargs["middleware"]]
    assert middleware_types == [
        EnvelopeLifecycleMiddleware,
        McpToolsMiddleware,
        McpToolAvailabilityMiddleware,
        RoleScopedToolsMiddleware,
        EnvelopeMiddleware,
        ChatAttachmentPreprocessingMiddleware,
        ScopedSkillsMiddleware,
    ]


def test_build_unified_without_args_passes_a_backend_factory() -> None:
    kwargs = _call_build_unified_and_capture_kwargs()
    assert kwargs["backend"] is not None
    assert callable(kwargs["backend"])


def test_build_unified_without_args_still_defaults_checkpointer_and_store_to_none() -> None:
    """Redundante com `test_build_unified_parametrization.py` de propósito:
    este arquivo sozinho já prova o cenário "sem regressão" completo, sem
    depender de outro arquivo de teste continuar existindo."""
    kwargs = _call_build_unified_and_capture_kwargs()
    assert kwargs["checkpointer"] is None
    assert kwargs["store"] is None
