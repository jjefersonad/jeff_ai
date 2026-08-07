"""Testes de integração: `PostgresMcpServerRepository` (task
`user-scoped-mcp-config-storage-task-store-2`).

Cobre os critérios de aceite da task:
- REQ-002: `save()` cifra os valores de `env`/`headers` antes de persistir —
  uma leitura crua do Postgres NÃO pode conter o plaintext original, e o
  round-trip preserva o tipo original (inclusive string puramente numérica).
- REQ-002: uma linha undecryptável com a chave ATIVA é logada e pulada por
  `list_by_user`, nunca derruba a leitura das demais linhas.
- REQ-001: `list_by_user` filtra por `user_id` — o servidor de outro usuário
  nunca aparece.

Requer `INTEGRATION_POSTGRES_URI` apontando para um Postgres real — mesmo
padrão de `test_user_integrations_repository.py`.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime

import psycopg
import pytest
from cryptography.fernet import Fernet

from src.domain.mcp import McpServerConfig
from src.infrastructure.auth.schema import ensure_schema as ensure_auth_schema
from src.infrastructure.persistence.user_mcp_servers_schema import ensure_schema

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
    """Garante tabelas `users` + `user_mcp_servers` e uma chave Fernet válida.

    Cada teste recebe sua própria chave Fernet e trunca `user_mcp_servers` —
    mesmo raciocínio de `test_user_integrations_repository.py`: como a chave
    muda por execução, uma linha sobrevivente de uma execução anterior nunca
    mais decifra e quebraria `list_by_user` (que varre todas as linhas do
    usuário, e uma delas corrompida não pode travar as demais).
    """
    monkeypatch.setenv("INTEGRATION_CREDENTIALS_KEY", Fernet.generate_key().decode())
    ensure_auth_schema(_uri())
    ensure_schema(_uri())

    def _truncate() -> None:
        with psycopg.connect(_uri()) as conn:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE user_mcp_servers")
            conn.commit()

    _truncate()
    yield
    # Trunca também depois: outros arquivos de teste (ex.:
    # `test_user_mcp_servers_schema.py`) fazem `SELECT count(*) ... WHERE
    # name = 'zernio'` sem escopo de usuário — uma linha "zernio" deixada
    # por este arquivo quebraria essa contagem se rodada na mesma sessão.
    _truncate()


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


def _new_http_server(
    user_id: str, name: str, headers: dict[str, str]
) -> McpServerConfig:
    return McpServerConfig(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name=name,
        transport="http",
        url="https://exemplo.com/mcp",
        headers=headers,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _raw_headers_column(user_id: str, server_id: str) -> str:
    """Lê a coluna `headers` persistida como texto (raw, sem decifrar)."""
    with psycopg.connect(_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT headers::text FROM user_mcp_servers "
                "WHERE id = %s AND user_id = %s",
                (server_id, user_id),
            )
            row = cur.fetchone()
    assert row is not None, f"row não encontrada: id={server_id}"
    return row[0]


async def test_save_persists_headers_as_ciphertext_and_round_trips_numeric_string() -> None:
    """unit-1 (REQ-002): leitura crua não contém o plaintext; round-trip
    preserva o tipo original, inclusive de uma string puramente numérica."""
    from src.infrastructure.persistence.mcp_server_repository import (
        PostgresMcpServerRepository,
    )

    user_id = _insert_test_user()
    plaintext_token = "super-secret-zernio-token-12345"
    numeric_header_value = "556199976245"
    repo = PostgresMcpServerRepository(_uri())
    server = _new_http_server(
        user_id,
        "zernio",
        {"Authorization": plaintext_token, "X-Numeric": numeric_header_value},
    )

    await repo.save(server)

    raw = _raw_headers_column(user_id, server.id)
    assert plaintext_token not in raw
    assert numeric_header_value not in raw
    parsed = json.loads(raw)
    assert "Authorization" in parsed

    fetched = await repo.get(user_id, "zernio")
    assert fetched is not None
    assert fetched.headers == {
        "Authorization": plaintext_token,
        "X-Numeric": numeric_header_value,
    }
    assert isinstance(fetched.headers["X-Numeric"], str)


async def test_list_by_user_skips_row_undecryptable_with_current_key() -> None:
    """unit-2 (REQ-002): uma linha cifrada com uma chave diferente da ativa
    (rotação/corrupção) é pulada e logada, sem derrubar as demais linhas do
    mesmo usuário."""
    from src.infrastructure.persistence.mcp_server_repository import (
        PostgresMcpServerRepository,
    )

    user_id = _insert_test_user()
    repo = PostgresMcpServerRepository(_uri())

    valid_server = _new_http_server(user_id, "zernio", {"Authorization": "still-valid"})
    await repo.save(valid_server)

    # Linha corrompida: cifrada com uma chave DIFERENTE da ativa no teste.
    orphaned_ciphertext = (
        Fernet(Fernet.generate_key())
        .encrypt(json.dumps("orphaned-token").encode())
        .decode()
    )
    orphaned_id = str(uuid.uuid4())
    with psycopg.connect(_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO user_mcp_servers "
                "(id, user_id, name, transport, url, headers, created_at, updated_at) "
                "VALUES (%s, %s, %s, 'http', %s, %s::jsonb, now(), now())",
                (
                    orphaned_id,
                    user_id,
                    "orphaned-server",
                    "https://exemplo.com/mcp",
                    json.dumps({"Authorization": {"__enc__": orphaned_ciphertext}}),
                ),
            )
        conn.commit()

    servers = await repo.list_by_user(user_id)

    by_id = {s.id: s for s in servers}
    assert by_id[valid_server.id].headers == {"Authorization": "still-valid"}
    assert orphaned_id not in by_id


async def test_list_by_user_returns_only_that_users_servers() -> None:
    """unit-3 (REQ-001): isolamento por `user_id` na camada de repositório —
    o servidor de outro usuário nunca aparece em `list_by_user`."""
    from src.infrastructure.persistence.mcp_server_repository import (
        PostgresMcpServerRepository,
    )

    user_a = _insert_test_user()
    user_b = _insert_test_user()
    repo = PostgresMcpServerRepository(_uri())
    server_a = _new_http_server(user_a, "zernio", {"Authorization": "token-a"})
    server_b = _new_http_server(user_b, "zernio", {"Authorization": "token-b"})
    await repo.save(server_a)
    await repo.save(server_b)

    servers_for_a = await repo.list_by_user(user_a)

    assert {s.id for s in servers_for_a} == {server_a.id}
    assert servers_for_a[0].headers == {"Authorization": "token-a"}
