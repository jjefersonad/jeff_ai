"""Docstring/skill surface for absolute image URLs (return-public-image-url)."""
from __future__ import annotations

from pathlib import Path

from src.agents.subagents import image_design as image_design_mod
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


def test_skill_and_subagent_prompt_use_url_not_path() -> None:
    skill = _SKILL.read_text(encoding="utf-8")
    assert "http://" in skill or "https://" in skill
    assert "/api/images/" in skill
    assert '"url": "/api/images/' not in skill
    assert "NÃO use `path`" in skill or "NÃO use path" in skill.lower()

    source = Path(image_design_mod.__file__).read_text(encoding="utf-8")
    assert "http://" in source or "https://" in source
    assert "/api/images/" in source
    assert "só `url`" in source or "só url" in source.lower()
    assert "![descrição](/api/images/" not in source
