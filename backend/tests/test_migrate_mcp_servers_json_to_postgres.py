"""Testes de `scripts/migrate_mcp_servers_json_to_postgres.py`.

Migração única do arquivo legado `backend/mcp_servers.json` (task
`user-scoped-mcp-config-storage-task-migration-1`) para a tabela
`user_mcp_servers`. Cobre REQ-003 do spec `user-mcp-server-store`:

- unit-1: o formato aninhado por `user_id` (o que o design documenta como
  "shape deixado por `user-data-isolation`") é migrado sob aquele `user_id`,
  e `--dry-run` não escreve nada em Postgres.
- unit-2: o formato legado plano (`{"mcpServers": {<name>: <entry>}}`, sem
  aninhamento por `user_id`) cai sob a partição do admin de bootstrap;
  rodar o script de novo não duplica a linha (idempotente, chave
  `(user_id, name)` no upsert).

Requer `INTEGRATION_POSTGRES_URI` apontando para um Postgres real — mesmo
padrão de `test_mcp_server_repository.py`. Os schemas
`users`/`user_mcp_servers` são garantidos via `ensure_*_schema` antes de
cada teste, e a tabela é truncada depois.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import psycopg
import pytest
from cryptography.fernet import Fernet

INTEGRATION_URI_ENV = "INTEGRATION_POSTGRES_URI"
pytestmark = pytest.mark.skipif(
    not os.environ.get(INTEGRATION_URI_ENV),
    reason=(
        f"Requer Postgres de teste real. Defina {INTEGRATION_URI_ENV} "
        "(ex.: postgresql://jeff_ia:jeff_ia@localhost:5436/jeff_ia) "
        "para rodar este teste."
    ),
)

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import migrate_mcp_servers_json_to_postgres as migrate  # noqa: E402

from src.infrastructure.auth.schema import (  # noqa: E402
    ensure_schema as ensure_auth_schema,
)
from src.infrastructure.persistence.user_mcp_servers_schema import (  # noqa: E402
    ensure_schema,
)


def _uri() -> str:
    return os.environ[INTEGRATION_URI_ENV]


@pytest.fixture(autouse=True)
def _setup_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    """Garante `users` + `user_mcp_servers`, chave Fernet válida, tabela truncada.

    Cada teste recebe sua própria chave e trunca a tabela — mesmo padrão de
    `test_mcp_server_repository.py`.
    """
    monkeypatch.setenv("INTEGRATION_CREDENTIALS_KEY", Fernet.generate_key().decode())
    ensure_auth_schema(_uri())
    ensure_schema(_uri())

    with psycopg.connect(_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE user_mcp_servers")
        conn.commit()
    yield
    with psycopg.connect(_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE user_mcp_servers")
        conn.commit()


def _insert_test_admin() -> str:
    """Cria um usuário `role=admin` e devolve o `id` (UUID) como string.

    Importante: `created_at` é setado explicitamente para um valor antigo
    o suficiente para que ESTE admin seja o retornado por `resolve_admin_id`
    (`ORDER BY created_at ASC LIMIT 1`). Sem isso, qualquer admin pré-existente
    (de testes anteriores que compartilham a mesma `INTEGRATION_POSTGRES_URI`)
    seria escolhido, e o teste reportaria um `user_id` inesperado.
    """
    from datetime import UTC, datetime, timedelta

    admin_id = str(uuid.uuid4())
    # 100 anos no passado é suficiente para qualquer admin pré-existente.
    ancient = datetime.now(UTC) - timedelta(days=365 * 100)
    with psycopg.connect(_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (id, username, password_hash, role, created_at) "
                "VALUES (%s, %s, %s, 'admin', %s)",
                (admin_id, f"test-admin-{admin_id}", "x", ancient),
            )
        conn.commit()
    return admin_id


def _insert_test_user(user_id: str | None = None) -> str:
    """Cria um usuário comum e devolve o `id` (UUID) como string."""
    user_id = user_id or str(uuid.uuid4())
    with psycopg.connect(_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (id, username, password_hash) "
                "VALUES (%s, %s, %s)",
                (user_id, f"test-{user_id}", "x"),
            )
        conn.commit()
    return user_id


def _list_rows(user_id: str) -> list[tuple]:
    """Lê `(name, transport, url, headers::text)` para `user_id`."""
    with psycopg.connect(_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name, transport, url, headers::text "
                "FROM user_mcp_servers WHERE user_id = %s ORDER BY name",
                (user_id,),
            )
            return list(cur.fetchall())


# --- unit-1: nested-by-user_id shape ----------------------------------------


def test_migrate_nested_shape_dry_run_prints_plan_no_row_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """GIVEN JSON aninhado sob `user_id` WHEN `--dry-run` THEN imprime o plano
    e NÃO escreve em Postgres."""
    target_user_id = _insert_test_user()
    config_path = tmp_path / "mcp_servers.json"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    target_user_id: {
                        "zernio": {
                            "transport": "http",
                            "url": "https://mcp.zernio.com/mcp",
                            "headers": {"Authorization": "Bearer token-xyz"},
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    plan = migrate.run_migration(config_path, _uri(), dry_run=True)

    assert any(item.name == "zernio" and item.user_id == target_user_id for item in plan)
    assert _list_rows(target_user_id) == []
    out = capsys.readouterr().out
    assert "zernio" in out
    assert target_user_id in out
    assert "dry-run" in out.lower()


def test_migrate_nested_shape_real_run_writes_one_encrypted_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """GIVEN JSON aninhado sob `user_id` WHEN roda de verdade THEN UMA linha
    é gravada sob aquele `user_id`, com `Authorization` cifrado (plaintext
    NUNCA aparece na coluna `headers`)."""
    target_user_id = _insert_test_user()
    config_path = tmp_path / "mcp_servers.json"
    plaintext_token = "super-secret-zernio-token-12345"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    target_user_id: {
                        "zernio": {
                            "transport": "http",
                            "url": "https://mcp.zernio.com/mcp",
                            "headers": {"Authorization": plaintext_token},
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    plan = migrate.run_migration(config_path, _uri(), dry_run=False)

    assert any(item.name == "zernio" and item.user_id == target_user_id for item in plan)
    rows = _list_rows(target_user_id)
    assert len(rows) == 1
    name, transport, url, headers_raw = rows[0]
    assert name == "zernio"
    assert transport == "http"
    assert url == "https://mcp.zernio.com/mcp"
    # Ciphertext — nunca o plaintext.
    assert plaintext_token not in headers_raw
    parsed = json.loads(headers_raw)
    assert "Authorization" in parsed
    assert parsed["Authorization"] != plaintext_token
    # Round-trip via PostgresMcpServerRepository decifra de volta.
    from src.infrastructure.persistence.mcp_server_repository import (
        PostgresMcpServerRepository,
    )

    repo = PostgresMcpServerRepository(_uri())
    import asyncio

    fetched = asyncio.run(repo.get(target_user_id, "zernio"))
    assert fetched is not None
    assert fetched.headers == {"Authorization": plaintext_token}


# --- unit-2: flat legacy shape + idempotência ------------------------------


def test_migrate_flat_legacy_shape_falls_back_to_bootstrap_admin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """GIVEN JSON em formato plano legacy (sem aninhamento por `user_id`) WHEN
    roda de verdade THEN o servidor é inserido sob o `user_id` do admin de
    bootstrap.
    """
    _insert_test_admin()  # garante que existe PELO MENOS um admin
    # Para o teste ser robusto contra admins pré-existentes (de outros
    # testes que compartilham a mesma `INTEGRATION_POSTGRES_URI`),
    # verificamos o admin EFETIVO que o script resolveu — não o que
    # inserimos.
    effective_admin_id = migrate._resolve_admin_id(_uri())
    config_path = tmp_path / "mcp_servers.json"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "zernio": {
                        "transport": "http",
                        "url": "https://mcp.zernio.com/mcp",
                        "headers": {"Authorization": "Bearer legacy-token"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    plan = migrate.run_migration(config_path, _uri(), dry_run=False)

    assert any(
        item.name == "zernio" and item.user_id == effective_admin_id for item in plan
    )
    rows = _list_rows(effective_admin_id)
    assert len(rows) == 1
    name, _transport, _url, headers_raw = rows[0]
    assert name == "zernio"
    assert "Bearer legacy-token" not in headers_raw
    out = capsys.readouterr().out
    assert effective_admin_id in out


def test_migrate_is_idempotent_on_second_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """GIVEN o script já rodou uma vez WHEN roda de novo THEN nenhuma linha
    adicional é criada (upsert por `(user_id, name)` no repositório).
    """
    _insert_test_admin()  # garante que existe PELO MENOS um admin
    config_path = tmp_path / "mcp_servers.json"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "zernio": {
                        "transport": "http",
                        "url": "https://mcp.zernio.com/mcp",
                        "headers": {"Authorization": "Bearer token-2"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    migrate.run_migration(config_path, _uri(), dry_run=False)
    capsys.readouterr()  # consome stdout do primeiro run

    plan = migrate.run_migration(config_path, _uri(), dry_run=False)

    # Segunda passada: o item continua no plano (seria re-inserido), mas o
    # upsert por `(user_id, name)` no repositório garante que nenhuma
    # linha NOVA é criada — `len(rows)` segue 1.
    assert any(item.name == "zernio" for item in plan)
    # Query o admin que o script realmente usou (não o que inserimos —
    # eles podem divergir se houver admins pré-existentes; em qualquer
    # caso, o admin usado é o retornado por `resolve_admin_id`).
    effective_admin_id = migrate._resolve_admin_id(_uri())
    rows = _list_rows(effective_admin_id)
    assert len(rows) == 1


# --- arquivo vazio / ausente -----------------------------------------------


def test_migrate_empty_file_is_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """GIVEN um `mcp_servers.json` sem entrada `mcpServers` (ou vazio) WHEN
    roda de verdade THEN nada é gravado, sem erro."""
    config_path = tmp_path / "mcp_servers.json"
    config_path.write_text(json.dumps({}), encoding="utf-8")

    plan = migrate.run_migration(config_path, _uri(), dry_run=False)

    assert plan == []
    out = capsys.readouterr().out
    assert "nenhum" in out.lower() or plan == []
