"""Carregamento unificado de variáveis de ambiente (bare-metal).

Reproduz em execução bare-metal (`python main.py`, `make dev`, `pytest`) a mesma
precedência que o Docker Compose já aplica entre `./.env` (bloco `environment:`,
usado para interpolação `${...}`) e `backend/.env` (`env_file:`): a raiz sempre
vence. Sem isso, `load_dotenv()` sem argumento só enxerga `backend/.env` (o CWD
é `backend/`), e as duas formas de rodar o projeto podem divergir silenciosamente
para chaves definidas nos dois arquivos (ex.: OLLAMA_MODEL).
"""

from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parents[2]  # backend/
_ROOT_DIR = _BACKEND_DIR.parent  # raiz do repo


def load_env() -> None:
    """Carrega `backend/.env` e, por cima, `./.env` (raiz vence em conflito)."""
    load_dotenv(_BACKEND_DIR / ".env")
    load_dotenv(_ROOT_DIR / ".env", override=True)
