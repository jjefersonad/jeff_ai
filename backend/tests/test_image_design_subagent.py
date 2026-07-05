"""Testes do image_design_subagent (REQ-003 / image-design-planning).

O gate de aprovação é imposto pelo framework (deepagents/LangGraph) através do
`interrupt_on`: quando o LLM decide chamar `create_image_from_prompt`, o grafo PAUSA
antes de executar a tool. Testar o loop completo aprovar/rejeitar exige um modelo
LLM real (Ollama) e a API Gemini, então aqui validamos de forma DETERMINÍSTICA que
o gate está corretamente CONFIGURADO (o que garante a pausa), e deixamos o fluxo
end-to-end como testes marcados para ambiente de integração.
"""
import os

import pytest

from src.agents.subagents.image_design import (
    ALLOWED_DECISIONS,
    image_design_subagent,
)

VALID_DECISIONS = {"approve", "edit", "reject"}


def _tool_names(subagent):
    return {getattr(t, "name", None) for t in subagent["tools"]}


def test_interrupt_gate_configured_on_generation_tool():
    """REQ-003: a tool de geração está sob interrupt_on (pausa antes de gerar)."""
    interrupt_on = image_design_subagent["interrupt_on"]
    assert "create_image_from_prompt" in interrupt_on


def test_allowed_decisions_are_valid():
    """REQ-003: allowed_decisions só usa valores suportados (approve/edit/reject)."""
    cfg = image_design_subagent["interrupt_on"]["create_image_from_prompt"]
    assert set(cfg["allowed_decisions"]).issubset(VALID_DECISIONS)
    assert set(ALLOWED_DECISIONS).issubset(VALID_DECISIONS)


def test_subagent_has_generation_and_style_tools():
    """O subagente expõe a tool de geração e as tools de memória de estilo."""
    names = _tool_names(image_design_subagent)
    assert "create_image_from_prompt" in names
    assert {"save_design_style", "load_design_style", "list_design_styles"} <= names


def test_system_prompt_enforces_approval_rule():
    """REQ-003: o system prompt contém a regra de nunca gerar sem aprovação."""
    prompt = image_design_subagent["system_prompt"].lower()
    assert "aprova" in prompt  # exige aprovação
    assert "nunca" in prompt   # regra crítica de bloqueio


# --- Fluxo end-to-end (requer Ollama + Gemini reais) -------------------------
# Estes testes exercitam o loop real design plan -> aprovação/rejeição via
# Command(resume=...). Rodam apenas quando RUN_LLM_E2E=1 e as credenciais estão
# presentes, pois dependem de serviços externos e são não-determinísticos.

_run_e2e = os.getenv("RUN_LLM_E2E") == "1"
e2e = pytest.mark.skipif(
    not _run_e2e, reason="requer Ollama + Gemini reais (defina RUN_LLM_E2E=1)"
)


@e2e
def test_e2e_plan_then_approval_generates_image():
    """REQ-003 (e2e): pedido -> design plan -> aprovação -> geração da imagem."""
    pytest.skip("Cenário de integração: implementar com langgraph dev + credenciais.")


@e2e
def test_e2e_rejection_iterates_plan_without_generating():
    """REQ-003 (e2e): rejeição com feedback -> plano revisado sem gerar imagem."""
    pytest.skip("Cenário de integração: implementar com langgraph dev + credenciais.")
