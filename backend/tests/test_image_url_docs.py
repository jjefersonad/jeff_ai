"""Docstring/skill surface for absolute image URLs (return-public-image-url)."""
from __future__ import annotations

from pathlib import Path

from src.tools.generate_image_tool import create_image_from_prompt

_SKILL = (
    Path(__file__).resolve().parents[1] / "skills" / "image-generation" / "SKILL.md"
)


def test_create_image_from_prompt_docstring_shows_absolute_url() -> None:
    doc = create_image_from_prompt.description or create_image_from_prompt.__doc__ or ""
    assert "http://" in doc or "https://" in doc
    assert "/api/images/" in doc
    assert "ALWAYS use" in doc
    assert '"url": "/api/images/' not in doc


def test_skill_prompt_uses_url_not_path() -> None:
    """A garantia de URL-não-path era checada em dois lugares: a skill e o
    `system_prompt` do `image_design_subagent`. O subagente foi deletado
    (`image-design-approval-gate` cutover-1) — a skill agora é a única
    fonte, e já carregava esta instrução antes mesmo desta change."""
    skill = _SKILL.read_text(encoding="utf-8")
    assert "http://" in skill or "https://" in skill
    assert "/api/images/" in skill
    assert '"url": "/api/images/' not in skill
    assert "NÃO use `path`" in skill or "NÃO use path" in skill.lower()
