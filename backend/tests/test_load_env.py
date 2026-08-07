"""Testes de `src.composition.env.load_env` — fonte única na raiz."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import src.composition.env as env_mod

_ROOT_KEY = "JEFF_AI_LOAD_ENV_ROOT_ONLY"
_BACKEND_ONLY_KEY = "JEFF_AI_LOAD_ENV_BACKEND_ONLY"


@pytest.fixture
def isolated_env_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Aponta load_env para um layout temporário com `.env` na raiz."""
    root = tmp_path / "repo"
    backend = root / "backend"
    backend.mkdir(parents=True)
    monkeypatch.setattr(env_mod, "_ROOT_DIR", root)
    monkeypatch.delenv(_ROOT_KEY, raising=False)
    monkeypatch.delenv(_BACKEND_ONLY_KEY, raising=False)
    return root, backend


def test_load_env_reads_root_without_backend_env(isolated_env_dirs):
    root, backend = isolated_env_dirs
    (root / ".env").write_text(f"{_ROOT_KEY}=from_root\n", encoding="utf-8")
    assert not (backend / ".env").exists()

    env_mod.load_env()

    assert os.environ[_ROOT_KEY] == "from_root"


def test_load_env_uses_root_when_backend_env_diverges(isolated_env_dirs):
    root, backend = isolated_env_dirs
    (root / ".env").write_text(
        f"{_ROOT_KEY}=from_root\n",
        encoding="utf-8",
    )
    (backend / ".env").write_text(
        f"{_ROOT_KEY}=from_backend\n{_BACKEND_ONLY_KEY}=backend_secret\n",
        encoding="utf-8",
    )

    env_mod.load_env()

    assert os.environ[_ROOT_KEY] == "from_root"
    # Root-only load: chaves só em backend/.env não entram em os.environ.
    assert _BACKEND_ONLY_KEY not in os.environ
