"""Backfill one-shot: atribui arquivos gerados pré-existentes ao admin de bootstrap.

Popula `generated_files` (resource-ownership-model REQ-003, task
`user-data-isolation-task-backfill-1`) para todo arquivo já presente em
`documents_dir/{docx,xlsx,pptx}` e `images_dir/*.png` no momento em que o
change `user-data-isolation` é implantado, atribuindo o dono ao primeiro
usuário `role admin` (o admin de bootstrap criado por
`src/infrastructure/auth/schema.py`). Roda uma vez, manualmente, no deploy —
não é chamado pela aplicação.

Idempotente via `ON CONFLICT (kind, filename) DO NOTHING`, a mesma
`UNIQUE(kind, filename)` de `src/infrastructure/ownership/schema.py`: rodar de
novo não duplica linhas nem move o ownership de arquivos já atribuídos.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

_DOCUMENT_KINDS = ("docx", "xlsx", "pptx")


class BackfillError(RuntimeError):
    """Pré-condição ausente para rodar o backfill (ex.: nenhum admin existe)."""


def find_existing_files(documents_dir: Path, images_dir: Path) -> list[tuple[str, str]]:
    """`(kind, filename)` de todo arquivo já existente em `documents_dir`/`images_dir`.

    Espelha exatamente o que `documents_router`/`images_router` já servem
    hoje: subdiretórios `docx`/`xlsx`/`pptx` em `documents_dir`, e apenas
    `*.png` em `images_dir` (mesmo filtro de `images_router.list_images`).
    Diretórios ausentes são tolerados (nenhum arquivo pré-existente daquele
    kind).
    """
    entries: list[tuple[str, str]] = []
    for kind in _DOCUMENT_KINDS:
        kind_dir = documents_dir / kind
        if not kind_dir.is_dir():
            continue
        for f in sorted(kind_dir.iterdir()):
            if f.is_file():
                entries.append((kind, f.name))

    if images_dir.is_dir():
        for f in sorted(images_dir.iterdir()):
            if f.is_file() and f.suffix.lower() == ".png":
                entries.append(("image", f.name))

    return entries


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


def run_backfill(
    conninfo: str,
    *,
    documents_dir: Path,
    images_dir: Path,
    dry_run: bool,
) -> list[tuple[str, str, str]]:
    """Executa (ou simula, em `dry_run`) o backfill.

    Retorna as linhas `(kind, filename, user_id)` inseridas — ou que seriam
    inseridas, em dry-run, sem gravar nada além da leitura do admin.
    """
    entries = find_existing_files(documents_dir, images_dir)

    with psycopg.connect(conninfo, autocommit=True) as conn:
        admin_id = resolve_admin_id(conn)

        if dry_run:
            return [(kind, filename, admin_id) for kind, filename in entries]

        inserted: list[tuple[str, str, str]] = []
        with conn.cursor() as cur:
            for kind, filename in entries:
                cur.execute(
                    "INSERT INTO generated_files (user_id, kind, filename) "
                    "VALUES (%s, %s, %s) ON CONFLICT (kind, filename) DO NOTHING "
                    "RETURNING id",
                    (admin_id, kind, filename),
                )
                if cur.fetchone() is not None:
                    inserted.append((kind, filename, admin_id))

    return inserted


def main() -> int:
    """CLI: roda o backfill (ou `--dry-run`) e sai com 0/1 conforme o resultado."""
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Lista o que seria inserido, sem gravar no banco.",
    )
    args = parser.parse_args()

    conninfo = os.environ.get("POSTGRES_URI")
    if not conninfo:
        print("ERRO: POSTGRES_URI não está definida.", file=sys.stderr)
        return 1

    documents_dir = Path(os.environ.get("DOCUMENTS_DIR", "/deps/backend/outputs/documents"))
    images_dir = Path(os.environ.get("IMAGES_DIR", "/deps/backend/outputs/images"))

    try:
        rows = run_backfill(
            conninfo, documents_dir=documents_dir, images_dir=images_dir, dry_run=args.dry_run
        )
    except BackfillError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1

    label = "seria(m) inserida(s)" if args.dry_run else "inserida(s)"
    print(f"{len(rows)} linha(s) {label} em generated_files:")
    for kind, filename, user_id in rows:
        print(f"  ({kind}, {filename}) -> user_id={user_id}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
