"""Testes dos assets/deps de geração PDF (add-pdf-creation-tool-task-deps-1)."""
from __future__ import annotations

from pathlib import Path

import tomllib

from src.infrastructure.documents.pdf_fonts import DEJAVU_SANS_PATH


_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_dejavu_sans_font_exists_and_is_readable() -> None:
    """Unit: fonte TTF canônica existe e é legível."""
    assert DEJAVU_SANS_PATH.is_file(), f"missing font at {DEJAVU_SANS_PATH}"
    assert DEJAVU_SANS_PATH.stat().st_size > 0
    # TTF magic: 0x00010000 or 'OTTO' / 'true'
    header = DEJAVU_SANS_PATH.read_bytes()[:4]
    assert header in {b"\x00\x01\x00\x00", b"OTTO", b"true", b"typ1"}


def test_pyproject_declares_fpdf2() -> None:
    """Unit: pyproject.toml lista a dependência fpdf2."""
    pyproject = _BACKEND_ROOT / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    assert any(dep.startswith("fpdf2") for dep in deps), deps
