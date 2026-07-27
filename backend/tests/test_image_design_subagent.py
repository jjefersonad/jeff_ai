"""Testes do image_design_subagent (image-design-planning).

A geração de imagem roda sem gate de aprovação humana: `create_image_from_prompt`
não está em `interrupt_on`. Validamos de forma DETERMINÍSTICA a configuração do
subagente; o fluxo end-to-end com LLM real fica marcado para integração.
"""
import os

import pytest

from src.agents.subagents.image_design import image_design_subagent


def _tool_names(subagent):
    return {getattr(t, "name", None) for t in subagent["tools"]}


def test_no_interrupt_gate_on_generation_tool():
    """create_image_from_prompt NÃO pausa o grafo — geração imediata."""
    interrupt_on = image_design_subagent.get("interrupt_on") or {}
    assert "create_image_from_prompt" not in interrupt_on


def test_subagent_has_generation_and_style_tools():
    """O subagente expõe a tool de geração e as tools de memória de estilo."""
    names = _tool_names(image_design_subagent)
    assert "create_image_from_prompt" in names
    assert {"save_design_style", "load_design_style", "list_design_styles"} <= names


def test_system_prompt_does_not_require_approval_gate():
    """O system prompt orienta geração imediata, sem gate de botões."""
    prompt = image_design_subagent["system_prompt"].lower()
    description = image_design_subagent["description"].lower()
    assert "sem gate" in prompt or "imediatamente" in prompt
    assert "interrupt_on" not in prompt
    assert "aprovação obrigatória" not in description


def test_system_prompt_limits_one_image_and_saves_style_after_success():
    """REQ-003/REQ-004: uma imagem por resposta; save_design_style após sucesso."""
    prompt = image_design_subagent["system_prompt"].lower()
    assert "uma" in prompt and "imagem" in prompt
    assert "save_design_style" in prompt
    assert "após a geração bem-sucedida" in prompt or "após sucesso" in prompt


# --- Fluxo end-to-end (requer Ollama + Gemini reais) -------------------------
# Estes testes exercitam o loop real design plan -> geração. Rodam apenas quando
# RUN_LLM_E2E=1 e as credenciais estão presentes.

_run_e2e = os.getenv("RUN_LLM_E2E") == "1"
e2e = pytest.mark.skipif(
    not _run_e2e, reason="requer Ollama + Gemini reais (defina RUN_LLM_E2E=1)"
)


@e2e
def test_e2e_plan_then_generates_image():
    """Pedido -> design plan -> geração da imagem (sem aprovação)."""
    pytest.skip("Cenário de integração: implementar com langgraph dev + credenciais.")
