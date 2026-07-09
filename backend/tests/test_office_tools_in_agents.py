"""Testes que as tools nativas de documentos estão registradas nos agentes.

Cobrem os critérios de aceitação da task `custom-office-doc-tools-task-integration-1`:
- REQ-001 (docx/xlsx/pptx): `create_docx_document`, `create_xlsx_spreadsheet` e
  `create_pptx_presentation` registradas na lista `tools=` do `assistant` e do
  `requirements_specialist`.
- Sem `interrupt_on`/subagente (geração direta, sem gate de aprovação).

Os agentes dependem de Ollama/Postgres em produção, mas a simples importação
dos módulos já valida o registro (create_deep_agent falharia na inicialização
se a lista de tools fosse inválida). Para tornar o teste hermético, mockamos
`create_deep_agent` para que ele capture a chamada sem tentar subir nada.
"""
from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest

TOOL_NAMES = (
    "create_docx_document",
    "create_xlsx_spreadsheet",
    "create_pptx_presentation",
)


def _capture_tools(call_args) -> list[object]:
    """Extrai a lista `tools=` passada para `create_deep_agent`."""
    if "tools" in call_args.kwargs:
        return list(call_args.kwargs["tools"])
    return list(call_args.args[call_args.kwargs.keys().__next__() and 1 : 1])  # fallback


@pytest.fixture
def fresh_modules(monkeypatch):
    """Recarrega os módulos dos agentes com `create_deep_agent` mockado.

    Importa `requirements_specialist` e `assistant/agent` capturando a chamada
    `create_deep_agent(...)` para inspecionar a lista de tools sem precisar de
    Ollama ou Postgres.
    """
    # Remove módulos já importados (caso testes anteriores tenham rodado).
    for mod in list(sys.modules):
        if mod.startswith("src.agents.requirements_specialist") or mod.startswith(
            "src.agents.assistant"
        ):
            del sys.modules[mod]

    with patch("deepagents.create_deep_agent") as mock_create:
        mock_create.return_value = MagicMock(name="agent")
        yield mock_create


def test_requirements_specialist_registers_office_tools(fresh_modules):
    """REQ-001: o orquestrador registra as 3 tools de documento."""
    importlib.import_module("src.agents.requirements_specialist")
    fresh_modules.assert_called_once()
    tools_arg = fresh_modules.call_args.kwargs["tools"]
    tool_names = {getattr(t, "name", None) for t in tools_arg}
    for name in TOOL_NAMES:
        assert name in tool_names, f"{name!r} não está em tools= do requirements_specialist"


def test_assistant_registers_office_tools(fresh_modules):
    """REQ-001: o assistant também registra as 3 tools de documento."""
    importlib.import_module("src.agents.assistant.agent")
    fresh_modules.assert_called_once()
    tools_arg = fresh_modules.call_args.kwargs["tools"]
    tool_names = {getattr(t, "name", None) for t in tools_arg}
    for name in TOOL_NAMES:
        assert name in tool_names, f"{name!r} não está em tools= do assistant"


def test_requirements_specialist_does_not_register_office_documents_via_interrupt(
    fresh_modules,
):
    """Sem `interrupt_on` para tools de documento (geração direta)."""
    importlib.import_module("src.agents.requirements_specialist")
    interrupt_on = fresh_modules.call_args.kwargs.get("interrupt_on", {}) or {}
    for name in TOOL_NAMES:
        assert name not in interrupt_on, (
            f"{name!r} não deve ter interrupt_on (geração direta, sem gate)."
        )


def test_assistant_does_not_register_office_documents_via_interrupt(fresh_modules):
    """Sem `interrupt_on` para tools de documento no assistant."""
    importlib.import_module("src.agents.assistant.agent")
    interrupt_on = fresh_modules.call_args.kwargs.get("interrupt_on", {}) or {}
    for name in TOOL_NAMES:
        assert name not in interrupt_on, (
            f"{name!r} não deve ter interrupt_on (geração direta, sem gate)."
        )


def test_requirements_specialist_uses_no_subagent_for_office_docs(fresh_modules):
    """Sem subagente dedicado para documentos Office (geração direta)."""
    importlib.import_module("src.agents.requirements_specialist")
    subagents = fresh_modules.call_args.kwargs.get("subagents", []) or []
    subagent_names = {getattr(s, "name", repr(s)) for s in subagents}
    # Os subagentes legítimos (fullstack, image_design) não devem ter nomes
    # parecidos com tools de documento.
    for name in TOOL_NAMES:
        assert not any(
            name in str(sn) for sn in subagent_names
        ), f"{name!r} não deve ser subagente."
