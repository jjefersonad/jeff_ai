"""Contratos de env em `docker-compose.yml` (fonte única na raiz + BASE_URL)."""
from __future__ import annotations

from pathlib import Path

import yaml

_COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yml"

# Topologia mínima preservada (REQ-ADD-004). pgadmin é profile `admin`.
_REQUIRED_SERVICES = frozenset(
    {
        "backend",
        "frontend",
        "jeff_ia_postgres",
        "jeff_ia_redis",
        "jeff_ia_pgadmin",
        "telegram_gateway",
    }
)


def _load_compose() -> dict:
    return yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))


def test_docker_compose_yml_preserves_services_and_root_env() -> None:
    data = _load_compose()
    services = data["services"]

    missing = _REQUIRED_SERVICES - set(services)
    assert not missing, f"serviços ausentes em docker-compose.yml: {sorted(missing)}"

    backend = services["backend"]
    env = backend.get("environment") or {}
    assert "BASE_URL" in env, "backend.environment deve propagar BASE_URL"
    assert "DOCUMENT_BASE_URL" not in env, (
        "DOCUMENT_BASE_URL não deve permanecer no environment do backend"
    )

    for name in ("backend", "telegram_gateway"):
        env_files = services[name].get("env_file") or []
        if isinstance(env_files, str):
            env_files = [env_files]
        assert ".env" in env_files, (
            f"{name}.env_file deve referenciar .env na raiz (got {env_files!r})"
        )
        assert "backend/.env" not in env_files, (
            f"{name}.env_file não deve mais apontar para backend/.env"
        )
