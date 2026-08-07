"""Carregamento unificado de variáveis de ambiente (bare-metal).

Fonte única: `./.env` na raiz do repositório. Compose e bare-metal
(`python main.py`, `make dev`, `pytest`) compartilham o mesmo arquivo —
não há dual-load com `backend/.env`.
"""

from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parents[2]  # backend/
_ROOT_DIR = _BACKEND_DIR.parent  # raiz do repo


def load_env() -> None:
    """Carrega apenas `./.env` (raiz do repositório)."""
    load_dotenv(_ROOT_DIR / ".env")
