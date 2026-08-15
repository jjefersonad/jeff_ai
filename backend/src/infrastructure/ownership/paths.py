"""Layout canônico `files/<user_id>/{attachment,images,docs}` (session-file-sandbox D5/D13)."""
from __future__ import annotations

import os
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_FILES_DIR = _BACKEND_ROOT / "files"

_DOC_KINDS = frozenset({"docx", "xlsx", "pptx", "pdf", "html"})
_KIND_TO_SUBDIR: dict[str, str] = {
    **{kind: "docs" for kind in _DOC_KINDS},
    "image": "images",
    "reference": "attachment",
}


def files_dir() -> Path:
    """Raiz canônica de arquivos por usuário (`FILES_DIR`, default `backend/files/`)."""
    raw = os.environ.get("FILES_DIR", "").strip()
    return Path(raw) if raw else _DEFAULT_FILES_DIR


def workspace_dir() -> Path:
    """Scratch per-thread (`WORKSPACE_DIR`, default `backend/workspace/`)."""
    raw = os.environ.get("WORKSPACE_DIR", "").strip()
    if raw:
        return Path(raw)
    return _BACKEND_ROOT / "workspace"


def kind_to_subdir(kind: str) -> str:
    """Mapa kind → subpasta sob `files/<user_id>/`.

    Raises
    ------
    ValueError
        Se `kind` não for conhecido.
    """
    try:
        return _KIND_TO_SUBDIR[kind]
    except KeyError as exc:
        raise ValueError(f"unknown generated_files kind: {kind!r}") from exc


def user_files_root(user_id: str) -> Path:
    """`FILES_DIR / <user_id>`."""
    if not user_id:
        raise ValueError("user_id is required")
    return files_dir() / user_id


def user_kind_dir(user_id: str, kind: str) -> Path:
    """Diretório físico para um kind: `files/<user_id>/{docs|images|attachment}`."""
    return user_files_root(user_id) / kind_to_subdir(kind)


def resolve_owned_file_path(*, user_id: str, kind: str, filename: str) -> Path:
    """Path derivado do layout (sem coluna `storage_path` em `generated_files`)."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise ValueError("invalid filename")
    return user_kind_dir(user_id, kind) / filename
