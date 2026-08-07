"""Contratos de `docker-compose.all.yml` — stack completa + env da raiz."""
from __future__ import annotations

from pathlib import Path

import yaml

_COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.all.yml"

_REQUIRED_SERVICES = frozenset(
    {
        "backend",
        "frontend",
        "jeff_ia_postgres",
        "jeff_ia_redis",
        "telegram_gateway",
        "ollama",
        "evolution_api",
        "evolution_postgres",
        "evolution_redis",
    }
)


def _load_compose() -> dict:
    assert _COMPOSE.is_file(), f"faltando {_COMPOSE.name}"
    return yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))


def test_all_compose_has_full_stack_and_internal_ollama_default() -> None:
    services = _load_compose()["services"]
    missing = _REQUIRED_SERVICES - set(services)
    assert not missing, f"serviços ausentes em docker-compose.all.yml: {sorted(missing)}"

    ollama_url = services["backend"]["environment"].get("OLLAMA_BASE_URL", "")
    assert "jeff_ia_ollama" in ollama_url, (
        "OLLAMA_BASE_URL default do backend deve apontar para o Ollama da rede Compose "
        f"(got {ollama_url!r})"
    )


def test_all_compose_uses_root_env_and_evolution_passwords() -> None:
    data = _load_compose()
    services = data["services"]
    text = _COMPOSE.read_text(encoding="utf-8")

    for name in ("backend", "telegram_gateway"):
        env_files = services[name].get("env_file") or []
        if isinstance(env_files, str):
            env_files = [env_files]
        assert ".env" in env_files, f"{name}.env_file deve referenciar .env (got {env_files!r})"
        assert "backend/.env" not in env_files

    env = services["backend"].get("environment") or {}
    assert "BASE_URL" in env
    assert "DOCUMENT_BASE_URL" not in env

    assert "EVOLUTION_POSTGRES_PASSWORD" in text
    assert "EVOLUTION_REDIS_PASSWORD" in text
