"""Deps canônicas de geração PDF (WeasyPrint) — pós cleanup fpdf2."""
from __future__ import annotations

from pathlib import Path

import tomllib

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_declares_weasyprint() -> None:
    """Unit: pyproject.toml lista WeasyPrint (não fpdf2)."""
    pyproject = _BACKEND_ROOT / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    assert any("weasyprint" in dep for dep in deps), deps
    assert not any("fpdf2" in dep for dep in deps), deps


def test_dockerfile_declares_weasyprint_not_fpdf2() -> None:
    """Unit: Dockerfile.backend pina weasyprint e não fpdf2."""
    dockerfile = (_BACKEND_ROOT / "Dockerfile.backend").read_text(encoding="utf-8")
    assert "weasyprint==" in dockerfile
    assert "fpdf2" not in dockerfile


def test_dockerfile_declares_jinja2() -> None:
    """Regressão: jinja2 no pip explícito (boot unified importa templates)."""
    dockerfile = (_BACKEND_ROOT / "Dockerfile.backend").read_text(encoding="utf-8")
    assert "jinja2==" in dockerfile
