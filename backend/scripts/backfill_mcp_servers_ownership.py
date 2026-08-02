"""Backfill one-shot: aninha o conteúdo global de `mcp_servers.json` sob o admin de bootstrap.

Anteriormente ao change `user-data-isolation` (task `mcp-1`),
`backend/mcp_servers.json` tinha um schema global
`{"mcpServers": {"<name>": <entrada>}}` — todo servidor era visível para todo
usuário. Após `mcp-1`, o schema é particionado por `user_id`
`{"mcpServers": {"<user_id>": {"<name>": <entrada>}}}`. Este script
(task `backfill-3`) pega o conteúdo que existia no schema global e o move
para a partição do primeiro usuário `role admin` (o admin de bootstrap
criado por `src/infrastructure/auth/schema.py`), cumprindo o item da
Migration Plan: "config de MCP: o conteúdo atual de `backend/mcp_servers.json`
(global) vira a config inicial do `admin` na nova estrutura por usuário".

## Detecção de schema

Um valor em `mcpServers` é tratado como entrada de servidor (formato
antigo) se contiver `command`, `url` ou `transport` ao nível superior.
Caso contrário, é tratado como partição (formato novo) — `{user_id: {nome:
entrada}}` — e fica intocado.

## Idempotência

Se a partição do admin já tiver um servidor com o mesmo nome (ex.: o admin
declarou um `opensddrag` novo após o bootstrap), o servidor legado é
**descartado** — o que está na partição do admin tem precedência, e nunca
sobrescrevemos uma escolha do admin. A entrada legada é removida do nível
raiz do JSON mesmo assim (estado misto não é válido para nenhum
consumidor) e o descarte é listado na saída do CLI. Rodar o script de
novo é seguro: ou não há nada legado a mover (file já está 100%
particionado) ou só move o que ainda está solto.

Roda uma vez, manualmente, no deploy — não é chamado pela aplicação.
Tem `--dry-run` para listar o que seria movido/descartado antes de gravar.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

# `backend/mcp_servers.json` — mesmo path que `src.agents.unified.mcp_client.DEFAULT_CONFIG_PATH`.
# Calculado aqui (em vez de importado) para que o script rode sem precisar
# do `src` no `PYTHONPATH` — o deploy pode chamá-lo diretamente
# (`python scripts/backfill_mcp_servers_ownership.py`).
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "mcp_servers.json"

_MCP_SERVERS_KEY = "mcpServers"

# Campos que só aparecem no nível de entrada de servidor (não no nível de
# partição). Usados pelo detector de schema — ver docstring do módulo.
_SERVER_ENTRY_FIELDS = frozenset({"command", "url", "transport"})


class BackfillError(RuntimeError):
    """Pré-condição ausente para rodar o backfill (ex.: nenhum admin existe)."""


def _is_server_entry(value: Any) -> bool:
    """Devolve `True` se `value` é uma entrada de servidor (formato antigo) e não uma partição.

    Heurística: se algum dos campos que só fazem sentido no nível de entrada
    de servidor (`command`/`url`/`transport`) está presente ao topo,
    classificamos como entrada. Partições do formato novo são dicts cujas
    chaves são `user_id` e cujos valores são entradas — eles não carregam
    `command`/`url`/`transport` no nível da partição.
    """
    return isinstance(value, dict) and any(field in value for field in _SERVER_ENTRY_FIELDS)


def _read_raw(path: Path) -> dict[str, Any]:
    """Lê o JSON cru. Arquivo ausente → `{}` (nada a migrar, não é erro)."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_raw(path: Path, raw: dict[str, Any]) -> None:
    """Grava o JSON de volta, no formato indentado que o resto do código usa."""
    path.write_text(
        json.dumps(raw, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def resolve_admin_id(conn: psycopg.Connection) -> str:
    """`id` do primeiro usuário `role admin` (o admin de bootstrap).

    Espelha o helper usado nos outros scripts de backfill do change
    (`backfill_generated_files_ownership.py`,
    `backfill_memories_namespace.py`) — mesma query, mesma regra de
    desempate (`created_at` ASC) e mesma exceção se não houver admin.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE role = 'admin' ORDER BY created_at LIMIT 1")
        row = cur.fetchone()
    if row is None:
        raise BackfillError(
            "Nenhum usuário admin encontrado — rode o bootstrap de autenticação "
            "(init_auth_schema) antes do backfill."
        )
    return str(row[0])


def collect_legacy_servers(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """`(nome -> entrada)` dos servidores que ainda estão no formato global antigo.

    Partições no formato novo ficam de fora — elas pertencem a um usuário
    específico e não devem ser movidas. Entradas que coincidentemente
    estejam sob uma chave com formato de UUID mas que carreguem campos
    de servidor também ficam de fora (são partições com nomes
    UUID-shaped, casos válidos do formato novo).
    """
    servers_root = raw.get(_MCP_SERVERS_KEY, {})
    return {
        name: entry
        for name, entry in servers_root.items()
        if _is_server_entry(entry)
    }


def run_backfill(
    config_path: Path,
    conninfo: str,
    *,
    dry_run: bool,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Executa (ou simula, em `dry_run`) o backfill.

    Retorna `(moved, skipped)`:

    - `moved`: `(server_name, admin_id)` de cada servidor legado movido
      sob a partição do admin — ou que seria movido, em dry-run.
    - `skipped`: `(server_name, admin_id)` de servidores legados
      descartados por colisão (admin já tem um servidor com o mesmo
      nome). Eles são removidos do nível raiz do JSON mesmo assim
      (estado misto não é válido para nenhum consumidor), mas a versão
      do admin tem precedência na partição.

    Em dry-run nada é gravado, mas a lista de `moved`/`skipped` é a
    mesma que seria em modo real — o caller (CLI) decide como exibir.
    Se o JSON lido não tiver nenhuma entrada legada (`legacy` vazio),
    o arquivo não é modificado (a função retorna listas vazias sem
    ter aberto uma conexão com Postgres).
    """
    raw = _read_raw(config_path)
    legacy = collect_legacy_servers(raw)
    if not legacy:
        return [], []

    with psycopg.connect(conninfo, autocommit=True) as conn:
        admin_id = resolve_admin_id(conn)

    servers_root = raw.setdefault(_MCP_SERVERS_KEY, {})
    admin_partition = servers_root.setdefault(admin_id, {})

    moved: list[tuple[str, str]] = []
    skipped: list[tuple[str, str]] = []
    for name, entry in legacy.items():
        if name in admin_partition:
            # Colisão: admin já tem este nome. Preserva o do admin,
            # descarta o legado — mas remove do nível raiz para não
            # deixar o JSON em estado misto.
            skipped.append((name, admin_id))
            continue
        if not dry_run:
            admin_partition[name] = entry
        moved.append((name, admin_id))

    # Regrava o arquivo se houver QUALQUER mudança (movida ou skip que
    # limpou o nível raiz). Em dry-run nunca grava.
    if not dry_run and (moved or skipped):
        for name, _ in (*moved, *skipped):
            servers_root.pop(name, None)
        # Se o `mcpServers` ficou vazio, mantenha a chave vazia (mesmo
        # formato que `mcp_config_store._read_raw` produz) — não é
        # problema para nenhum consumidor.
        _write_raw(config_path, raw)

    return moved, skipped


def main() -> int:
    """CLI: roda o backfill (ou `--dry-run`) e sai com 0/1 conforme o resultado."""
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Lista o que seria movido, sem gravar no arquivo.",
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=_DEFAULT_CONFIG_PATH,
        help=(
            "Caminho do mcp_servers.json. Default: o mesmo usado por "
            "mcp_client (backend/mcp_servers.json)."
        ),
    )
    args = parser.parse_args()

    conninfo = os.environ.get("POSTGRES_URI")
    if not conninfo:
        print("ERRO: POSTGRES_URI não está definida.", file=sys.stderr)
        return 1

    try:
        moved, skipped = run_backfill(args.config_path, conninfo, dry_run=args.dry_run)
    except BackfillError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1

    if not moved and not skipped:
        print("Nenhum servidor no formato global antigo — mcp_servers.json já está particionado.")
        return 0

    if moved:
        label = "seria(m) movido(s)" if args.dry_run else "movido(s)"
        print(f"{len(moved)} servidor(es) {label} para a partição do admin de bootstrap:")
        for name, admin_id in moved:
            print(f"  {name} -> mcpServers[{admin_id}][{name}]")

    if skipped:
        label = "seria(m) descartado(s)" if args.dry_run else "descartado(s)"
        print(f"{len(skipped)} servidor(es) legado(s) {label} por colisão (admin já tinha o mesmo nome):")
        for name, _ in skipped:
            print(f"  {name} (versão do admin preservada)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
