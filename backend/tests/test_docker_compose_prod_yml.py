"""Contratos de `docker-compose.prod.yml` — app-only + env da raiz."""
from __future__ import annotations

from pathlib import Path

import yaml

_COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.prod.yml"
_APP_SERVICES = frozenset({"backend", "frontend"})


def _load_compose() -> dict:
    return yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))


def test_prod_compose_services_are_exactly_frontend_and_backend() -> None:
    services = set(_load_compose()["services"])
    assert services == _APP_SERVICES, (
        f"prod deve declarar exatamente {_APP_SERVICES}, got {services}"
    )
    assert "telegram_gateway" not in services


def test_prod_backend_uses_root_env_file_and_base_url() -> None:
    backend = _load_compose()["services"]["backend"]
    env_files = backend.get("env_file") or []
    if isinstance(env_files, str):
        env_files = [env_files]
    assert ".env" in env_files, f"env_file deve referenciar .env na raiz (got {env_files!r})"
    assert "backend/.env" not in env_files

    env = backend.get("environment") or {}
    assert "BASE_URL" in env, "backend.environment deve propagar BASE_URL"
    assert "DOCUMENT_BASE_URL" not in env
