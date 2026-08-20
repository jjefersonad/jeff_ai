"""Testes do fluxo de geração de imagem (`image-design-approval-gate`).

Não existe mais um subagente dedicado (`image_design_subagent`, deletado por
`image-design-approval-gate` cutover-1) — a especialização de planejamento
vive em `backend/skills/image-generation/SKILL.md` e as tools no flat tool
set do agente `unified`. Este arquivo cobre as garantias que antes viviam no
`system_prompt` do subagente (uma string Python) e agora vivem no conteúdo
da skill (um arquivo markdown): aprovação obrigatória, uma imagem por
aprovação, salvar estilo após sucesso, e reject pedindo ajuste em vez de
retry automático.

Cobertura de tier/gate (`create_image_from_prompt` é Tier 3 e entra no
`interrupt_on`) já está em `test_tier_config.py` e `test_effects.py` — não
duplicada aqui, exceto por uma checagem-ponte mínima para este arquivo não
voltar a afirmar "sem gate".
"""
from pathlib import Path

_SKILL_PATH = (
    Path(__file__).resolve().parent.parent / "skills" / "image-generation" / "SKILL.md"
)


def _skill_text() -> str:
    return _SKILL_PATH.read_text(encoding="utf-8").lower()


def test_skill_requires_approval_gate_not_immediate_generation() -> None:
    """A skill não instrui geração imediata nem confirmação textual — o
    gate é o `interrupt_on` (approval-ux REQ-001)."""
    text = _skill_text()
    assert "interrupt_on" in text
    assert "geração imediata" not in text
    assert "sem gate de aprovação" not in text


def test_skill_limits_one_image_per_approval() -> None:
    """approval-ux REQ-003: uma imagem por aprovação."""
    assert "uma imagem por aprovação" in _skill_text()


def test_skill_instructs_saving_style_after_success() -> None:
    assert "save_design_style" in _skill_text()


def test_skill_instructs_asking_for_adjustment_on_reject() -> None:
    """approval-ux REQ-005: reject pede ajuste, não retry automático."""
    text = _skill_text()
    assert "reject" in text
    assert "ajuste" in text


def test_create_image_from_prompt_is_still_gated() -> None:
    """Checagem-ponte: este arquivo (herdeiro dos testes do subagente
    deletado) não pode voltar a assumir 'sem gate'."""
    from src.agents.unified.tier_config import get_tier

    assert get_tier("create_image_from_prompt") == 3
