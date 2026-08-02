"""Testes de `src/infrastructure/telegram/migration.py` (task
`user-integration-credentials-task-migration-1`).

Cobre a auto-migração do vínculo Telegram legado (`TELEGRAM_AUTHORIZED_CHAT_ID`)
para o admin mais antigo, na primeira subida do gateway após o deploy
(design Migration Plan passo 2, REQ-002 do delta `telegram-channel`).

Requer `INTEGRATION_POSTGRES_URI` apontando para um Postgres real — mesmo
padrão de `test_user_integrations_repository.py`.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from cryptography.fernet import Fernet

from src.domain.integrations import UserIntegration
from src.infrastructure.auth.schema import ensure_schema as ensure_auth_schema
from src.infrastructure.persistence.user_integrations_repository import (
    PostgresUserIntegrationRepository,
)
from src.infrastructure.persistence.user_integrations_schema import ensure_schema
from src.infrastructure.telegram.migration import auto_migrate_legacy_chat_binding

INTEGRATION_URI_ENV = "INTEGRATION_POSTGRES_URI"
pytestmark = pytest.mark.skipif(
    not os.environ.get(INTEGRATION_URI_ENV),
    reason=(
        f"Requer Postgres de teste real. Defina {INTEGRATION_URI_ENV} "
        "(ex.: postgresql://jeff_ia:jeff_ia@localhost:5436/jeff_ia) "
        "para rodar este teste."
    ),
)


def _uri() -> str:
    return os.environ[INTEGRATION_URI_ENV]


@pytest.fixture(autouse=True)
def _setup_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    """Garante tabelas `users` + `user_integrations` limpas e uma chave Fernet válida.

    Mesmo racional de `test_user_integrations_repository.py`: cada teste
    recebe sua própria chave Fernet, e as tabelas são truncadas antes de
    cada teste (`CASCADE` cobre a FK `user_integrations.user_id`).
    """
    monkeypatch.setenv("INTEGRATION_CREDENTIALS_KEY", Fernet.generate_key().decode())
    ensure_auth_schema(_uri())
    ensure_schema(_uri())
    with psycopg.connect(_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE user_integrations, sessions, users CASCADE")
        conn.commit()


def _insert_user(*, role: str, created_at: datetime) -> str:
    user_id = str(uuid.uuid4())
    with psycopg.connect(_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (id, username, password_hash, role, created_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (user_id, f"test-{user_id}", "x", role, created_at),
            )
        conn.commit()
    return user_id


def _telegram_row_count() -> int:
    with psycopg.connect(_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM user_integrations WHERE integration_type = 'telegram'"
            )
            row = cur.fetchone()
    return row[0] if row else 0


def test_auto_migrate_binds_chat_id_to_earliest_admin() -> None:
    """unit-1: zero linhas telegram + chat_id legado → vínculo p/ admin mais antigo.

    Síncrono de propósito: `auto_migrate_legacy_chat_binding` chama
    `asyncio.run()` internamente (mesmo contrato de uso do `main()` real do
    gateway, que também é síncrono nesse ponto do bootstrap) — rodar o
    teste dentro de um event loop já ativo (via `pytest-asyncio`) quebraria
    esse `asyncio.run()` aninhado.
    """
    now = datetime.now(UTC)
    later_admin = _insert_user(role="admin", created_at=now)
    earliest_admin = _insert_user(role="admin", created_at=now - timedelta(days=1))
    _insert_user(role="user", created_at=now - timedelta(days=2))

    auto_migrate_legacy_chat_binding(
        postgres_uri=_uri(), authorized_chat_id="legacy-chat-id-123"
    )

    assert _telegram_row_count() == 1
    repo = PostgresUserIntegrationRepository(_uri())
    entries = asyncio.run(repo.list_all())
    assert len(entries) == 1
    assert entries[0].user_id == earliest_admin
    assert entries[0].user_id != later_admin
    assert entries[0].config == {"chat_id": "legacy-chat-id-123"}


def test_auto_migrate_is_noop_when_telegram_row_already_exists() -> None:
    """unit-2: já existe linha telegram (de qualquer usuário) → não insere nem modifica nada."""
    admin_id = _insert_user(role="admin", created_at=datetime.now(UTC))
    repo = PostgresUserIntegrationRepository(_uri())
    existing = UserIntegration(
        id=str(uuid.uuid4()),
        user_id=admin_id,
        integration_type="telegram",
        config={"chat_id": "already-linked-chat"},
    )
    asyncio.run(repo.save(existing))

    auto_migrate_legacy_chat_binding(
        postgres_uri=_uri(), authorized_chat_id="should-not-be-inserted"
    )

    assert _telegram_row_count() == 1
    entries = asyncio.run(repo.list_all())
    assert entries[0].config == {"chat_id": "already-linked-chat"}
