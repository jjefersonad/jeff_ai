"""Migra o conteúdo de `backend/mcp_servers.json` para a tabela Postgres `user_mcp_servers`.

Task `user-scoped-mcp-config-storage-task-migration-1`. Cumpre REQ-003 do spec
`user-mcp-server-store`: lê o(s) servidor(es) hoje presentes em
`backend/mcp_servers.json` (incluindo a variante aninhada por `user_id`
documentada no design como o "shape deixado por `user-data-isolation`") e os
grava na nova tabela, cifrando `env`/`headers` via `PostgresMcpServerRepository`
(mesmo helper, mesma chave, mesmo envelope — ver design Decision 2).

## Shapes suportados

1. **Aninhado por `user_id`** (`{mcpServers: {<user_id>: {<name>: <entry>}}}`):
   o `user_id` da chave é preservado — o servidor vai sob a partição daquele
   usuário, sem perguntar a ninguém.
2. **Flat legacy** (`{mcpServers: {<name>: <entry>}}`, sem aninhamento por
   `user_id`): o servidor cai sob o `user_id` do admin de bootstrap
   (`resolve_admin_id`), mesmo fallback usado por
   `backfill_mcp_servers_ownership.py` e `backfill_memories_namespace.py` para
   o período pré-`user-data-isolation`.

## Detecção de schema

Reusa exatamente a heurística de `backfill_mcp_servers_ownership.py`: um
valor em `mcpServers` é classificado como **entrada de servidor** (formato
antigo/flat) se contiver `command`, `url` ou `transport` ao nível superior;
caso contrário, é classificado como **partição** (formato novo/nested) — um
dict cujas chaves são `user_id` e cujos valores são entradas.

## Resolução de `${VAR}`

A runtime de `mcp_client.build_connection` resolve `${VAR}` em
`env`/`headers` lendo `os.environ` — mas isso SÓ funciona quando o
processo do agente tem a env var no contexto. A migração **resolve agora**
(substitui `${VAR}` pelo valor real) e grava o valor real no banco; o
agente, ao ler, recebe o valor pronto e `_resolve_env_value` no `mcp_client`
fica como no-op para esse formato exato. Assim, tokens como `ZERNIO_API_TOKEN`
chegam corretamente ao servidor MCP independente do contexto de execução do
worker que faz a leitura.

## Idempotência

`save()` no `PostgresMcpServerRepository` faz `INSERT ... ON CONFLICT
(user_id, name) DO UPDATE` (task-store-2) — rodar o script duas vezes não
cria linhas duplicadas, apenas reescreve os mesmos `(user_id, name)`.

## CLI

```
python scripts/migrate_mcp_servers_json_to_postgres.py [--dry-run] [--config-path PATH]
```

`--dry-run` imprime o plano sem conectar a Postgres (se a config não tiver
nada a migrar, também não conecta). Em modo real, conecta a Postgres para
resolver o admin de bootstrap (se houver entrada flat) e para cada upsert
via `PostgresMcpServerRepository` — que abre uma conexão por operação
(mesmo padrão do resto do código).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

# Mesmo path default que `mcp_client.DEFAULT_CONFIG_PATH` (`backend/mcp_servers.json`).
# Calculado aqui (em vez de importado) para que o script rode sem precisar
# do `src` no `PYTHONPATH` — o deploy pode chamá-lo diretamente.
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "mcp_servers.json"

_MCP_SERVERS_KEY = "mcpServers"

# Campos que só aparecem no nível de entrada de servidor (não no nível de
# partição). Usados pelo detector de schema — mesma heurística de
# `backfill_mcp_servers_ownership.py`.
_SERVER_ENTRY_FIELDS = frozenset({"command", "url", "transport"})

# `${VAR}` exato — única forma suportada de carregar credencial no formato
# arquivo (mesma regex de `mcp_client._ENV_VAR_PATTERN`).
_ENV_VAR_PATTERN = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


class MigrationError(RuntimeError):
    """Pré-condição ausente para rodar a migração (ex.: nenhum admin existe)."""


@dataclass(frozen=True)
class MigrationItem:
    """Uma entrada de servidor destinada a ser inserida em `user_mcp_servers`.

    `user_id` é o dono do servidor: vem direto da chave do JSON no formato
    aninhado, ou do admin de bootstrap no formato flat legacy.
    `entry` é a forma validada por `McpServerEntryConfig` (campos
    obrigatórios por `transport` já garantidos).
    """

    user_id: str
    name: str
    transport: str
    command: str | None
    args: list[str]
    url: str | None
    env: dict[str, str]
    headers: dict[str, str]


def _is_server_entry(value: Any) -> bool:
    """Verifica se `value` é uma entrada de servidor (formato antigo/flat) e não uma partição.

    Heurística: se algum dos campos que só fazem sentido no nível de entrada
    de servidor (`command`/`url`/`transport`) está presente ao topo,
    classificamos como entrada. Partições do formato novo (nested) são
    dicts cujas chaves são `user_id` e cujos valores são entradas — elas NÃO
    carregam `command`/`url`/`transport` no nível da partição.
    """
    return isinstance(value, dict) and any(field in value for field in _SERVER_ENTRY_FIELDS)


def _resolve_env_value(raw: str) -> str:
    """Substitui `${VAR}` por `os.environ['VAR']`.

    Mesma regra de `mcp_client._resolve_env_value`: a única forma
    suportada de passar credencial é por referência a variável de ambiente.
    Um valor que não casa o padrão é devolvido como está (permite valores
    não-secretos, ex.: URLs, hard-coded no config). Aqui a diferença
    importante: ao contrário do `mcp_client`, este script resolve NO
    MOMENTO DA MIGRAÇÃO — o valor REAL vai para o banco (criptografado).
    """
    match = _ENV_VAR_PATTERN.match(raw)
    if match is None:
        return raw
    var_name = match.group(1)
    if var_name not in os.environ:
        raise MigrationError(
            f"variável de ambiente '{var_name}' referenciada em "
            "mcp_servers.json não está definida (esperada em backend/.env)."
        )
    return os.environ[var_name]


def _resolve_values(values: dict[str, str] | None) -> dict[str, str]:
    """Substitui `${VAR}` em cada valor de `env`/`headers`."""
    return {k: _resolve_env_value(v) for k, v in (values or {}).items()}


def _read_raw(path: Path) -> dict[str, Any]:
    """Lê o JSON cru. Arquivo ausente → `{}` (nada a migrar, não é erro)."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_entry(name: str, entry: dict[str, Any]) -> MigrationItem:
    """Valida FORMA de uma entrada (`McpServerEntryConfig`) e devolve um item de migração.

    Levanta `MigrationError` (com mensagem clara) se a forma estiver errada
    — o caller (CLI) exibe e aborta, em vez de gravar meia-entrada em Postgres.
    """
    # Import local para evitar arrastar o `src` para o `sys.path` quando o
    # script for importado em teste a partir de `tests/scripts/...`.
    from src.application.mcp.mcp_server_schema import McpServerEntryConfig

    try:
        validated = McpServerEntryConfig.model_validate(entry)
    except Exception as exc:  # noqa: BLE001 — qualquer erro de validação vira MigrationError
        raise MigrationError(
            f"entrada '{name}' inválida: {exc}"
        ) from exc

    return MigrationItem(
        user_id="",  # preenchido pelo caller (nested = da chave; flat = admin)
        name=name,
        transport=validated.transport,
        command=validated.command,
        args=list(validated.args),
        url=validated.url,
        env=_resolve_values(validated.env),
        headers=_resolve_values(validated.headers),
    )


def _collect_nested(raw: dict[str, Any]) -> list[MigrationItem]:
    """Coleta entradas no formato aninhado por `user_id`.

    Cada chave de `mcpServers` é um `user_id`; cada valor `{<name>: <entry>}`
    é a lista de servidores daquele usuário. Entradas no formato flat dentro
    dessa partição (heurística `_is_server_entry`) ficam de fora — elas
    pertencem ao formato flat legacy, tratados em `_collect_flat`.
    """
    servers_root = raw.get(_MCP_SERVERS_KEY, {})
    items: list[MigrationItem] = []
    for user_id, partition in servers_root.items():
        if not isinstance(partition, dict):
            continue
        if _is_server_entry(partition):
            # Formato flat misturado num dict que parecia partição — pula.
            continue
        for name, entry in partition.items():
            if not _is_server_entry(entry):
                # Defesa: entrada malformada aninhada. Pula silenciosamente
                # — o caller imprime os itens válidos depois.
                continue
            item = _validate_entry(name, entry)
            items.append(
                MigrationItem(
                    user_id=str(user_id),
                    name=item.name,
                    transport=item.transport,
                    command=item.command,
                    args=item.args,
                    url=item.url,
                    env=item.env,
                    headers=item.headers,
                )
            )
    return items


def _collect_flat(raw: dict[str, Any]) -> list[MigrationItem]:
    """Coleta entradas no formato flat legacy.

    Cada chave de `mcpServers` é o NOME de um servidor; cada valor é a
    entrada. O `user_id` é resolvido depois (admin de bootstrap) — aqui
    fica vazio.
    """
    servers_root = raw.get(_MCP_SERVERS_KEY, {})
    items: list[MigrationItem] = []
    for name, entry in servers_root.items():
        if not _is_server_entry(entry):
            continue
        item = _validate_entry(name, entry)
        items.append(item)
    return items


def _resolve_admin_id(conninfo: str) -> str:
    """`id` do primeiro usuário `role admin` (admin de bootstrap).

    Espelha `backfill_mcp_servers_ownership.resolve_admin_id` — mesma
    query, mesma regra de desempate (`created_at ASC`), mesma exceção.
    """
    with psycopg.connect(conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM users WHERE role = 'admin' ORDER BY created_at LIMIT 1"
            )
            row = cur.fetchone()
    if row is None:
        raise MigrationError(
            "Nenhum usuário admin encontrado — rode o bootstrap de autenticação "
            "(init_auth_schema) antes da migração."
        )
    return str(row[0])


def _assign_admin(items: list[MigrationItem], admin_id: str) -> None:
    """Preenche `user_id` dos itens flat com `admin_id` (in-place)."""
    for item in items:
        if not item.user_id:
            object.__setattr__(item, "user_id", admin_id)


def _save_items(
    items: list[MigrationItem],
    conninfo: str,
) -> None:
    """Grava cada item via `PostgresMcpServerRepository` em UM único event loop.

    O repositório é async (`save`/`get`), e este script é CLI sync — uma
    única chamada a `asyncio.run` cobre todos os itens (criar N event
    loops seria desperdício; um loop só abre uma vez e reusa).
    """
    # Import local para manter o script utilizável sem `src` no PYTHONPATH
    # em ambientes sem o pacote instalado (caso o deploy use formato egg).
    from src.domain.mcp import McpServerConfig
    from src.infrastructure.persistence.mcp_server_repository import (
        PostgresMcpServerRepository,
    )

    repo = PostgresMcpServerRepository(conninfo)

    async def _save_all() -> None:
        for item in items:
            # Verifica existência antes de inserir — o upsert do repositório
            # já é idempotente, mas pular explicitamente deixa o relatório
            # claro (não confunde "atualizou" com "inseriu novo" para o
            # operador que revisa o dry-run).
            if await repo.get(item.user_id, item.name) is not None:
                print(f"  [skip] {item.name} (já existe para user_id={item.user_id})")
                continue
            server = McpServerConfig(
                id=str(uuid.uuid4()),
                user_id=item.user_id,
                name=item.name,
                transport=item.transport,
                command=item.command,
                args=item.args,
                url=item.url,
                env=item.env,
                headers=item.headers,
            )
            await repo.save(server)
            print(f"  [insert] {item.name} -> user_mcp_servers[user_id={item.user_id}]")

    asyncio.run(_save_all())


def run_migration(
    config_path: Path,
    conninfo: str,
    *,
    dry_run: bool,
) -> list[MigrationItem]:
    """Executa (ou simula, em `dry_run`) a migração.

    Retorna a lista de `MigrationItem` que foram (ou seriam) inseridos.
    Itens já presentes em `user_mcp_servers` (mesmo `(user_id, name)`) NÃO
    são removidos do plano — o upsert no repositório garante idempotência
    no nível do banco, e o caller pode usar o retorno para exibir o que
    aconteceu.

    Detecção de schema:
    - Se `mcpServers` tiver QUALQUER chave cujo valor é entrada de servidor
      (heurística `_is_server_entry`), o arquivo é flat legacy.
    - Senão, é tratado como aninhado por `user_id` (cada chave = `user_id`,
      valor = dict de servidores).

    Em `dry_run`, **não conecta a Postgres** — então o admin de bootstrap
    não é resolvido, e o `_user_id` dos itens flat fica vazio (o caller
    sabe que a saída de dry-run para flat é "o admin resolveria em
      produção" — o print do plano deixa isso explícito).
    """
    raw = _read_raw(config_path)
    nested = _collect_nested(raw)
    flat = _collect_flat(raw)

    if not nested and not flat:
        print("Nenhum servidor em mcp_servers.json — nada a migrar.")
        return []

    if dry_run:
        # Em dry-run: imprime o que SERIA feito, sem tocar em Postgres.
        print("DRY-RUN: nenhuma alteração será gravada.\n")
        for item in nested:
            print(f"  [aninhado] {item.name} -> user_mcp_servers[user_id={item.user_id}]")
        for item in flat:
            print(
                f"  [flat legacy] {item.name} -> user_mcp_servers[user_id=<admin de bootstrap>] "
                f"(resolvido em produção: primeiro users.role='admin' ORDER BY created_at)"
            )
        return nested + flat

    # Modo real: resolve admin uma vez (só se houver itens flat).
    if flat:
        admin_id = _resolve_admin_id(conninfo)
        _assign_admin(flat, admin_id)

    items = nested + flat
    _save_items(items, conninfo)
    return items


def main() -> int:
    """CLI: roda a migração (ou `--dry-run`) e sai com 0/1 conforme o resultado."""
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Imprime o plano de migração sem gravar em Postgres.",
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
        items = run_migration(args.config_path, conninfo, dry_run=args.dry_run)
    except MigrationError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"\n{len(items)} servidor(es) listados acima.")
    else:
        print(f"\n{len(items)} servidor(es) processados.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
