"""Paths canônicos das fontes TTF usadas na geração de PDF (fpdf2).

As fontes ficam empacotadas em `backend/assets/fonts/` para que dev e prod
usem o mesmo arquivo — sem download em runtime e sem depender de pacotes
do sistema operacional.
"""
from __future__ import annotations

from pathlib import Path

# backend/src/infrastructure/documents/pdf_fonts.py → backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_FONTS_DIR = _BACKEND_ROOT / "assets" / "fonts"

DEJAVU_SANS_PATH: Path = _FONTS_DIR / "DejaVuSans.ttf"
DEJAVU_SANS_BOLD_PATH: Path = _FONTS_DIR / "DejaVuSans-Bold.ttf"
