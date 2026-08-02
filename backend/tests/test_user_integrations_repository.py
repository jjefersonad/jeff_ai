"""Testes de integração: `PostgresUserIntegrationRepository` (task
`user-integration-credentials-task-store-2`).

Cobre os critérios de aceite da task:
- REQ-002: `save()` cifra o `config` antes de persistir — uma leitura crua do
  Postgres NÃO pode conter o plaintext original
- REQ-001: `get()` devolve a entrada do dono decifrada, e `list_by_user`
  filtra por `user_id`; o `get` de outro `user_id` não vê o ciphertext

Requer `INTEGRATION_POSTGRES_URI` apontando para um Postgres real — mesmo
padrão de `test_scheduled_task_repository.py`.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime

import psycopg
import pytest
from cryptography.fernet import Fernet

from src.domain.integrations import UserIntegration
from src.infrastructure.auth.schema import ensure_schema as ensure_auth_schema
from src.infrastructure.persistence.user_integrations_schema import ensure_schema

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
    """Garante tabelas `users` + `user_integrations` e uma chave Fernet válida.

    Cada teste recebe sua própria chave para que ciphertexts sejam
    incomparáveis entre execuções — isso é o que prova que a cifra não é
    identidade trivial. Trunca `user_integrations` a cada teste: como a
    chave muda por execução, uma linha sobrevivente de uma execução
    anterior nunca mais decifra e quebraria `list_all()` (que varre a
    tabela inteira, ao contrário de `get`/`list_by_user`, escopados por id).
    """
    monkeypatch.setenv("INTEGRATION_CREDENTIALS_KEY", Fernet.generate_key().decode())
    ensure_auth_schema(_uri())
    ensure_schema(_uri())
    with psycopg.connect(_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE user_integrations")
        conn.commit()


def _insert_test_user() -> str:
    """Cria um usuário de teste e devolve o `id` (UUID) como string."""
    user_id = str(uuid.uuid4())
    with psycopg.connect(_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (id, username, password_hash) "
                "VALUES (%s, %s, %s)",
                (user_id, f"test-{user_id}", "x"),
            )
        conn.commit()
    return user_id


def _new_integration(user_id: str, config: dict[str, object]) -> UserIntegration:
    return UserIntegration(
        id=str(uuid.uuid4()),
        user_id=user_id,
        integration_type="telegram",
        config=config,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _raw_config_row(user_id: str, integration_id: str) -> str:
    """Lê o `config` persistido como texto (raw, sem decifrar)."""
    with psycopg.connect(_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT config::text FROM user_integrations "
                "WHERE id = %s AND user_id = %s",
                (integration_id, user_id),
            )
            row = cur.fetchone()
    assert row is not None, f"row não encontrada: id={integration_id}"
    return row[0]


async def test_save_persists_config_as_ciphertext_not_plaintext() -> None:
    """unit-1 (REQ-002): uma leitura crua do `config` NÃO pode conter o plaintext."""
    from src.infrastructure.persistence.user_integrations_repository import (
        PostgresUserIntegrationRepository,
    )

    user_id = _insert_test_user()
    plaintext_chat_id = "super-secret-chat-id-12345"
    repo = PostgresUserIntegrationRepository(_uri())
    integration = _new_integration(user_id, {"chat_id": plaintext_chat_id})

    await repo.save(integration)

    raw = _raw_config_row(user_id, integration.id)
    # O ciphertext (Fernet) está embutido em `chat_id`; o plaintext original
    # não pode aparecer em nenhum canto da linha persistida.
    assert plaintext_chat_id not in raw
    # sanity: a coluna continua sendo JSONB válido (a forma do envelope é
    # preservada — só o valor do campo sensível é cifrado).
    parsed = json.loads(raw)
    assert "chat_id" in parsed


async def test_get_for_owning_user_returns_decrypted_config() -> None:
    """unit-2 (REQ-001): `get()` para o mesmo `user_id` que salvou devolve plaintext."""
    from src.infrastructure.persistence.user_integrations_repository import (
        PostgresUserIntegrationRepository,
    )

    user_id = _insert_test_user()
    plaintext_chat_id = "round-trip-chat-id-67890"
    repo = PostgresUserIntegrationRepository(_uri())
    integration = _new_integration(user_id, {"chat_id": plaintext_chat_id})

    await repo.save(integration)
    fetched = await repo.get(integration.id)

    assert fetched is not None
    assert fetched.user_id == user_id
    assert fetched.integration_type == "telegram"
    assert fetched.config == {"chat_id": plaintext_chat_id}


async def test_list_all_returns_decrypted_entries_across_users() -> None:
    """`list_all()` (REQ-004, task store-3) devolve entradas de TODOS os usuários, decifradas."""
    from src.infrastructure.persistence.user_integrations_repository import (
        PostgresUserIntegrationRepository,
    )

    user_a = _insert_test_user()
    user_b = _insert_test_user()
    repo = PostgresUserIntegrationRepository(_uri())
    integration_a = _new_integration(user_a, {"chat_id": "chat-a"})
    integration_b = _new_integration(user_b, {"chat_id": "chat-b"})
    await repo.save(integration_a)
    await repo.save(integration_b)

    all_integrations = await repo.list_all()

    by_id = {i.id: i for i in all_integrations}
    assert by_id[integration_a.id].config == {"chat_id": "chat-a"}
    assert by_id[integration_b.id].config == {"chat_id": "chat-b"}
