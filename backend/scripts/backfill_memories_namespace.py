"""Backfill one-shot: move memórias do namespace legado para o namespace do admin de bootstrap.

Move cada entrada no namespace global legado `("memories",)` (anterior ao
change `user-data-isolation`, hoje vazio em produção mas ainda mantido no
schema para evitar perda de dados) para o namespace por-usuário
`("memories", admin_id)` — onde `admin_id` é o primeiro usuário com
`role = 'admin'` (o admin de bootstrap criado por
`src/infrastructure/auth/schema.py`). Após este backfill, as memórias
legadas só são retornadas em buscas feitas pelo admin (REQ-003 de
`scoped-memory-namespace`), nunca em buscas de outros usuários.

O Store do LangGraph persiste namespaces como texto dot-separated
(`("memories",)` → `prefix = "memories"`, `("memories", user_id)` →
`prefix = "memories.<user_id>"`, ver `_namespace_to_text` em
`langgraph/store/postgres/base.py`). O filtro do `list_legacy_keys` é
portanto exato (`prefix = 'memories'`), não `LIKE 'memories.%'` — esse
último pegaria os namespaces por-usuário já em uso.

Move também as linhas de `store_vectors` (chave estrangeira com `ON DELETE
CASCADE` partindo de `store(prefix, key)`), re-inscrevendo-as sob o novo
prefixo — assim o índice semântico continua respondendo pelas memórias
movidas sem precisar re-embedar (que exigiria uma chamada ao modelo de
embedding, fora do escopo de um script one-shot de migração).

Roda uma vez, manualmente, no deploy — não é chamado pela aplicação.
Idempotente: se a coluna `("memories",)` já estiver vazia, o script
simplesmente não faz nada (sem erro).
"""

from __future__ import annotations

import argparse
import os
import sys

import psycopg
from dotenv import load_dotenv

LEGACY_PREFIX = "memories"  # dot-separated form do namespace `("memories",)`
VECTOR_TABLE = "store_vectors"


class BackfillError(RuntimeError):
    """Pré-condição ausente para rodar o backfill (ex.: nenhum admin existe)."""


def list_legacy_keys(conn: psycopg.Connection) -> list[str]:
    """Chaves (`key`) no namespace legado `("memories",)`.

    Filtro exato por `prefix`: namespaces por-usuário
    (`("memories", <user_id>)` → `"memories.<user_id>"`) NÃO devem ser
    capturados — eles já estão sob a custódia do dono correto.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT key FROM store WHERE prefix = %s ORDER BY key", (LEGACY_PREFIX,))
        rows = cur.fetchall()
    return [row[0] for row in rows]


def resolve_admin_id(conn: psycopg.Connection) -> str:
    """`id` do primeiro usuário `role admin` (o admin de bootstrap)."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE role = 'admin' ORDER BY created_at LIMIT 1")
        row = cur.fetchone()
    if row is None:
        raise BackfillError(
            "Nenhum usuário admin encontrado — rode o bootstrap de autenticação "
            "(init_auth_schema) antes do backfill."
        )
    return str(row[0])


def _move_one(
    cur: psycopg.Cursor,
    *,
    legacy_prefix: str,
    new_prefix: str,
    key: str,
) -> None:
    """Move uma única chave do namespace legado para o novo, junto com seus vetores.

    Lê a linha de `store` (value, created_at, updated_at) e de
    `store_vectors` (uma ou mais linhas por (prefix, key), uma por
    `field_name` indexado), re-inscreve ambas sob o novo prefixo, e
    deleta a linha original de `store` — o `ON DELETE CASCADE` da FK de
    `store_vectors` cuida dos vetores legados remanescentes.
    """
    cur.execute(
        "SELECT value, created_at, updated_at FROM store WHERE prefix = %s AND key = %s",
        (legacy_prefix, key),
    )
    row = cur.fetchone()
    if row is None:
        return
    value, created_at, updated_at = row

    cur.execute(
        "SELECT field_name, embedding, created_at, updated_at FROM store_vectors "
        "WHERE prefix = %s AND key = %s",
        (legacy_prefix, key),
    )
    vectors = cur.fetchall()

    cur.execute(
        "INSERT INTO store (prefix, key, value, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT (prefix, key) DO NOTHING",
        (new_prefix, key, value, created_at, updated_at),
    )
    for field_name, embedding, vec_created_at, vec_updated_at in vectors:
        cur.execute(
            f"INSERT INTO {VECTOR_TABLE} (prefix, key, field_name, embedding, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (prefix, key, field_name) DO NOTHING",
            (new_prefix, key, field_name, embedding, vec_created_at, vec_updated_at),
        )
    cur.execute(
        "DELETE FROM store WHERE prefix = %s AND key = %s",
        (legacy_prefix, key),
    )


def run_backfill(
    conninfo: str,
    *,
    dry_run: bool,
) -> list[tuple[str, str]]:
    """Executa (ou simula, em `dry_run`) o backfill.

    Retorna as entradas `(key, admin_id)` movidas — ou que seriam movidas,
    em dry-run, sem gravar nada além da leitura do admin e da listagem
    das chaves legadas. Tudo dentro de uma única transação: se qualquer
    `_move_one` falhar no meio, `conn.rollback()` fecha a transação sem
    deixar o namespace legado em estado parcialmente migrado.
    """
    with psycopg.connect(conninfo) as conn:
        admin_id = resolve_admin_id(conn)
        keys = list_legacy_keys(conn)
        new_prefix = f"{LEGACY_PREFIX}.{admin_id}"

        if dry_run:
            return [(key, admin_id) for key in keys]

        moved: list[tuple[str, str]] = []
        try:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                for key in keys:
                    _move_one(
                        cur,
                        legacy_prefix=LEGACY_PREFIX,
                        new_prefix=new_prefix,
                        key=key,
                    )
                    moved.append((key, admin_id))
                cur.execute("COMMIT")
        except Exception:
            # O BEGIN explícito acima abriu a transação lógica; se algo
            # falhar antes do COMMIT, `conn.rollback()` fecha sem deixar
            # estado parcial (REQ-003: namespace legado consistente).
            conn.rollback()
            raise

    return moved


def main() -> int:
    """CLI: roda o backfill (ou `--dry-run`) e sai com 0/1 conforme o resultado."""
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Lista o que seria movido, sem gravar no banco.",
    )
    args = parser.parse_args()

    conninfo = os.environ.get("POSTGRES_URI")
    if not conninfo:
        print("ERRO: POSTGRES_URI não está definida.", file=sys.stderr)
        return 1

    try:
        rows = run_backfill(conninfo, dry_run=args.dry_run)
    except BackfillError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1

    label = "seria(m) movida(s)" if args.dry_run else "movida(s)"
    print(f"{len(rows)} memória(s) legada(s) {label} para o namespace do admin de bootstrap:")
    for key, admin_id in rows:
        print(f"  (memories, {key}) -> (memories, {admin_id})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
