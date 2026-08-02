"""Monkey-patch para o bug upstream `langgraph-checkpoint-postgres>=3.0.2`.

## Contexto
A função privada
`langgraph.checkpoint.postgres.base._build_delta_stage2_sql` constrói
uma `UNION ALL` entre dois branches ("w" lendo de `checkpoint_writes`
e "b" lendo de `checkpoint_blobs"). Na versão `>=3.0.2,<3.2.0`, o
branch "b" hard-coda `NULL::text AS checkpoint_id` e
`NULL::text AS task_id`, mas o schema criado pela mesma versão da
lib define essas colunas como `uuid`. Postgres não consegue fazer
matching de tipos `uuid` vs `text` numa `UNION` e aborta com
`psycopg.errors.DatatypeMismatch: UNION types uuid and text cannot
be matched`. Confirmado em produção (2026-07-24, tool de pesquisa no
Telegram) e reproduzido com o SQL exato via `psql`.

## Estratégia
Substitui `_build_delta_stage2_sql` por uma versão que faz a mesma
construção de SQL mas com `NULL::uuid` no branch "b" — alinhando os
casts com o schema real. A função original fica referenciada
internamente para preservar a semântica; só o SQL é corrigido.

## Idempotência
- A função `install_postgres_uuid_patch()` é segura para chamar
  múltiplas vezes. O segundo call é no-op (a função já está
  substituída).
- Se a lib upstream já tiver sido corrigida (gera `NULL::uuid` sem
  patch), `install_postgres_uuid_patch()` é no-op — não sobrescreve
  a versão corrigida.

## Onde é chamado
Importado e invocado uma única vez no topo de
`src/infrastructure/agent_runtime/langgraph_direct_runner.py`, antes
de qualquer uso de `AsyncPostgresSaver`/`AsyncPostgresStore`.

## Quando remover
Quando `langgraph-checkpoint-postgres>=3.2.0` for fixado no projeto
(na imagem `langchain/langgraph-api:3.11` ou no `pyproject.toml`) e
a SQL gerada pela função original já contiver `NULL::uuid` — o
patch vira no-op e pode ser removido.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Flag de módulo: marca que o patch já foi instalado nesta execução
# do Python. Usado para tornar `install_postgres_uuid_patch()`
# idempotente em chamadas múltiplas (sem precisar re-introspect a
# função toda vez). Acesso via globals() para tolerar `delattr` em
# testes e `importlib.reload`.
_PATCH_INSTALLED_ATTR = "_PATCH_INSTALLED"


def _generate_patched_sql(
    *,
    channels_with_chain: tuple[str, ...],
    channels_with_seed: tuple[str, ...],
) -> str:
    """Réplica de `_build_delta_stage2_sql` com `NULL::uuid` no branch "b".

    Preserva 100% do algoritmo da lib upstream (mesma estrutura de
    branches, mesma ordem de colunas, mesmos aliases) — só troca
    `NULL::text AS checkpoint_id` e `NULL::text AS task_id` por
    `NULL::uuid AS checkpoint_id` e `NULL::uuid AS task_id` no
    branch "b". Isso casa o cast com o tipo real da coluna no schema
    (`uuid` no schema criado por `langgraph-checkpoint-postgres>=3.0.2`).
    """
    branches: list[str] = []
    for _ in channels_with_chain:
        branches.append(
            "SELECT 'w'::text AS _kind, "
            "checkpoint_id, channel, "
            "type, blob, task_id, idx, NULL::text AS version "
            "FROM checkpoint_writes "
            "WHERE thread_id = %s AND checkpoint_ns = %s AND channel = %s "
            "AND checkpoint_id = ANY(%s)"
        )
    for _ in channels_with_seed:
        branches.append(
            # FIX: NULL::uuid (em vez de NULL::text) — match com o
            # tipo real das colunas no schema da lib
            # `langgraph-checkpoint-postgres>=3.0.2`.
            "SELECT 'b'::text AS _kind, NULL::uuid AS checkpoint_id, channel, "
            "type, blob, NULL::uuid AS task_id, NULL::int AS idx, version "
            "FROM checkpoint_blobs "
            "WHERE thread_id = %s AND checkpoint_ns = %s AND channel = %s "
            "AND version = %s"
        )
    return " UNION ALL ".join(branches)


def _is_lib_already_fixed(original_fn: Any) -> bool:
    """Detecta se a lib upstream já tem o fix.

    Estratégia: invoca a função original com inputs dummy e checa
    se a SQL gerada já contém `NULL::uuid AS checkpoint_id` no
    branch "b". Se sim, a lib está corrigida e o patch é no-op.

    Funciona em QUALQUER implementação da função (não depende do
    source, do nome dos parâmetros, ou do shape do retorno) — só
    do que a SQL realmente emite.
    """
    try:
        sql = original_fn(
            channels_with_chain=(),
            channels_with_seed=("__start__",),
        )
    except Exception:  # noqa: BLE001 — qualquer falha aqui é "não corrigido"
        return False
    return isinstance(sql, str) and "NULL::uuid AS checkpoint_id" in sql


def install_postgres_uuid_patch() -> None:
    """Substitui `langgraph.checkpoint.postgres.base._build_delta_stage2_sql`
    por uma versão que gera SQL compatível com o schema `uuid` da
    mesma versão da lib.

    Idempotente: chamada múltiplas vezes não causa efeito após a
    primeira. No-op em libs já corrigidas (não sobrescreve a versão
    oficial da upstream).

    Seguro em import lazy: se a lib
    `langgraph.checkpoint.postgres.base` não estiver instalada (e.g.
    em CI rodando só este arquivo isolado), loga um warning e
    retorna sem erro.
    """
    # Lê o flag via globals() para tolerar `delattr` em testes e
    # `importlib.reload` (que pode re-inicializar o módulo).
    if globals().get(_PATCH_INSTALLED_ATTR, False):
        # Patch já aplicado nesta execução — não sobrescreve.
        return

    try:
        from langgraph.checkpoint.postgres import base as lgcp_base
    except ImportError:
        logger.warning(
            "langgraph.checkpoint.postgres.base não está disponível; "
            "patch UUID não aplicado. A langgraph-checkpoint-postgres "
            "está instalada?"
        )
        return

    if not hasattr(lgcp_base, "_build_delta_stage2_sql"):
        logger.warning(
            "langgraph.checkpoint.postgres.base não tem "
            "_build_delta_stage2_sql — versão da lib não é compatível "
            "com este patch (talvez seja >=3.2.0 e já está corrigida, "
            "ou é uma versão muito antiga). Patch UUID não aplicado."
        )
        return

    original_fn = lgcp_base._build_delta_stage2_sql

    if _is_lib_already_fixed(original_fn):
        logger.info(
            "langgraph.checkpoint.postgres já gera SQL com "
            "NULL::uuid AS checkpoint_id — patch UUID é no-op "
            "(versão upstream provavelmente já consertou o bug)."
        )
        globals()[_PATCH_INSTALLED_ATTR] = True
        return

    # `aio` e o saver sync (`__init__`) fazem
    # `from ...base import _build_delta_stage2_sql` — binding por nome no
    # import. Patchar só `base._build_delta_stage2_sql` NÃO atualiza esses
    # namespaces; o Telegram/runner continua executando a SQL com
    # `NULL::text` e estoura `DatatypeMismatch`. Propagamos o patch para
    # todos os módulos que já importaram o símbolo.
    lgcp_base._build_delta_stage2_sql = _generate_patched_sql
    _rebind_imported_stage2_sql(_generate_patched_sql)

    globals()[_PATCH_INSTALLED_ATTR] = True
    logger.info(
        "Patch UUID aplicado em "
        "langgraph.checkpoint.postgres.base._build_delta_stage2_sql "
        "(e rebind em aio/__init__) — branch 'b' agora usa NULL::uuid "
        "em vez de NULL::text, compatível com o schema uuid criado por "
        "langgraph-checkpoint-postgres>=3.0.2."
    )


def _rebind_imported_stage2_sql(patched_fn: Any) -> None:
    """Atualiza `_build_delta_stage2_sql` nos módulos que já o importaram.

    Sem isto o monkey-patch em `base` é inócuo: `AsyncPostgresSaver`
    (`aio.py`) e `PostgresSaver` (`__init__.py`) guardam a referência
    original no namespace do módulo.
    """
    module_names = (
        "langgraph.checkpoint.postgres.aio",
        "langgraph.checkpoint.postgres",
    )
    for name in module_names:
        try:
            mod = __import__(name, fromlist=["_build_delta_stage2_sql"])
        except ImportError:
            continue
        if hasattr(mod, "_build_delta_stage2_sql"):
            setattr(mod, "_build_delta_stage2_sql", patched_fn)
