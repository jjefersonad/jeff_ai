"""Testes do monkey-patch para o bug upstream `langgraph-checkpoint-postgres>=3.0.2`.

Cobre a task `fix-langgraph-postgres-uuid-union-bug-task-patch-1`:

- REQ-001 cenário "Patch aplica corretamente em lib com bug"
  (`-unit-1`): quando a lib tem o bug
  (`_build_delta_stage2_sql` gera `NULL::text AS checkpoint_id` no
  branch "b"), `install_postgres_uuid_patch()` MUST substituir a
  função por uma versão cuja SQL gerada contém
  `NULL::uuid AS checkpoint_id` e `NULL::uuid AS task_id`.
- REQ-001 cenário "Patch é no-op em lib já corrigida" (`-unit-2`):
  quando a lib já gera `NULL::uuid`, `install_postgres_uuid_patch()`
  MUST NOT substituir a função.
- REQ-001 cenário "Patch idempotente" (`-unit-3`): chamar
  `install_postgres_uuid_patch()` duas vezes seguidas MUST NOT alterar
  a função entre a 1ª e a 2ª chamada.
- REQ-002 cenário "SQL com a UNION modificada roda sem
  DatatypeMismatch" (`-unit-4`): a SQL gerada pela função patchada
  MUST ser executável contra um schema uuid (validado por introspecção
  do SQL — duas branches "w" e "b", casts `NULL::uuid` no branch "b").

Estratégia: o teste opera em cima da função real da lib
(`langgraph.checkpoint.postgres.base._build_delta_stage2_sql`) — não
mocka nem reescreve a função alvo. Antes de cada teste, captura o
objeto-função original; depois, restaura. Isso garante que cada
teste é independente e que o teste reflete o estado real da lib
instalada no ambiente.
"""
from __future__ import annotations

import importlib
from typing import Any

import pytest

# Import lazy para que o teste não falhe se a lib não estiver instalada
# (e.g. em CI rodando só este arquivo isolado).
lgcp_base = pytest.importorskip("langgraph.checkpoint.postgres.base")

# Se a lib instalada não tem a função que vamos patchar, pula
# silenciosamente — provavelmente é uma versão muito antiga ou muito
# nova (já corrigida) onde o patch não se aplica.
if not hasattr(lgcp_base, "_build_delta_stage2_sql"):
    pytest.skip(
        "langgraph.checkpoint.postgres.base não tem "
        "_build_delta_stage2_sql — versão da lib não é compatível "
        "com este patch",
        allow_module_level=True,
    )

from src.infrastructure.agent_runtime import (  # noqa: E402
    _langgraph_postgres_uuid_patch as patch_mod,
)


def _reload_checkpoint_modules() -> None:
    """Recarrega `base` + módulos que importam `_build_delta_stage2_sql` por nome."""
    importlib.reload(lgcp_base)
    for name in (
        "langgraph.checkpoint.postgres.aio",
        "langgraph.checkpoint.postgres",
    ):
        try:
            mod = importlib.import_module(name)
        except ImportError:
            continue
        importlib.reload(mod)


@pytest.fixture
def restore_patch() -> Any:
    """Captura o estado original do módulo e restaura após o teste.

    Garante que cada teste é independente: o monkey-patch não vaza entre
    testes, e a função original da lib é restaurada mesmo se o teste
    falhar no meio.

    Estratégia: força um reload de `base` + `aio`/`__init__` no setup para
    garantir que estamos capturando a função ORIGINAL (não uma
    versão patchada por um teste anterior, nem a versão patchada
    instalada em runtime no boot do `langgraph_direct_runner.py`).
    Sem o reload, testes rodando após outros testes que importam
    `langgraph_direct_runner` veriam a função já patchada, o que
    dispara o "lib already fixed" skip indevidamente.
    """
    _reload_checkpoint_modules()
    # Limpa o flag do patch também — garante idempotência cross-test.
    # `install_postgres_uuid_patch` grava `_PATCH_INSTALLED` no dict do módulo.
    patch_mod.__dict__.pop("_PATCH_INSTALLED", None)
    original_fn = lgcp_base._build_delta_stage2_sql
    yield original_fn
    # Cleanup: restaura o estado original (em caso de exceção no meio).
    _reload_checkpoint_modules()
    patch_mod.__dict__.pop("_PATCH_INSTALLED", None)


# ---------------------------------------------------------------------------
# Unit-1: patch aplica corretamente em lib com bug
# ---------------------------------------------------------------------------


def test_install_postgres_uuid_patch_replaces_function_with_uuid_casts(
    restore_patch: Any,
) -> None:
    """Unit-1 (REQ-001 cenário "Patch aplica corretamente em lib com bug").

    Given: a lib instalada tem o bug (a função original gera SQL com
    `NULL::text AS checkpoint_id` no branch "b").

    When: `install_postgres_uuid_patch()` é chamado.

    Then: a função instalada em
    `langgraph.checkpoint.postgres.base._build_delta_stage2_sql` é
    diferente da original, e a SQL gerada pela nova função contém
    `NULL::uuid AS checkpoint_id` e `NULL::uuid AS task_id` no
    branch "b" (em vez de `NULL::text`).

    RED: hoje, sem o patch, a SQL gerada contém `NULL::text AS
    checkpoint_id` (o bug). GREEN: após o patch, contém
    `NULL::uuid AS checkpoint_id`.
    """
    original_fn = restore_patch

    # Em uma lib já corrigida (caso a upstream conserte no futuro), o
    # teste é pulado — este teste cobre especificamente o caso "lib com
    # bug". Para forçar o branch "b" (que tem o bug) a aparecer, é
    # preciso passar `channels_with_seed` não-vazio.
    sql_with_bug = original_fn(
        channels_with_chain=("messages",),
        channels_with_seed=("__start__",),
    )
    if "NULL::uuid AS checkpoint_id" in sql_with_bug:
        pytest.skip(
            "lib upstream já consertou o bug — unit-1 não se aplica"
        )

    # Confirma que a lib realmente tem o bug (sanity check).
    assert "NULL::text AS checkpoint_id" in sql_with_bug, (
        f"Pré-condição do teste falhou: a lib não tem o bug esperado. "
        f"SQL gerada: {sql_with_bug!r}"
    )

    # Aplica o patch.
    patch_mod.install_postgres_uuid_patch()

    # A função instalada no módulo agora deve ser diferente da
    # original.
    installed_fn = lgcp_base._build_delta_stage2_sql
    assert installed_fn is not original_fn, (
        "install_postgres_uuid_patch() não substituiu a função no "
        "módulo da lib upstream"
    )

    # A SQL gerada pela função patchada deve ter `NULL::uuid` no
    # branch "b". Forçamos um branch "b" passando `channels_with_seed`
    # não-vazio.
    sql_patched = installed_fn(
        channels_with_chain=(),
        channels_with_seed=("__start__",),
    )
    assert "NULL::uuid AS checkpoint_id" in sql_patched, (
        f"SQL patchada não contém `NULL::uuid AS checkpoint_id`: "
        f"{sql_patched!r}"
    )
    assert "NULL::uuid AS task_id" in sql_patched, (
        f"SQL patchada não contém `NULL::uuid AS task_id`: "
        f"{sql_patched!r}"
    )
    # E NÃO deve mais ter `NULL::text` no branch "b" (a substituição
    # aconteceu).
    assert "NULL::text AS checkpoint_id" not in sql_patched, (
        f"SQL patchada ainda contém `NULL::text AS checkpoint_id` "
        f"(patch não funcionou): {sql_patched!r}"
    )
    assert "NULL::text AS task_id" not in sql_patched, (
        f"SQL patchada ainda contém `NULL::text AS task_id` "
        f"(patch não funcionou): {sql_patched!r}"
    )


def test_install_postgres_uuid_patch_rebinds_aio_namespace(
    restore_patch: Any,
) -> None:
    """O patch MUST atualizar `aio._build_delta_stage2_sql` (import-by-name).

    `AsyncPostgresSaver.aget_delta_channel_history` chama o símbolo local
    do módulo `aio`, não `base._build_delta_stage2_sql`. Sem rebind, o
    Telegram continua com o bug mesmo com `base` patchado.
    """
    aio = pytest.importorskip("langgraph.checkpoint.postgres.aio")
    original_fn = restore_patch

    sql_with_bug = original_fn(
        channels_with_chain=("messages",),
        channels_with_seed=("__start__",),
    )
    if "NULL::uuid AS checkpoint_id" in sql_with_bug:
        pytest.skip("lib upstream já consertou o bug — rebind test N/A")

    # Simula o boot real: aio já importou o símbolo antes do patch.
    assert aio._build_delta_stage2_sql is original_fn

    patch_mod.install_postgres_uuid_patch()

    assert aio._build_delta_stage2_sql is lgcp_base._build_delta_stage2_sql
    sql_aio = aio._build_delta_stage2_sql(
        channels_with_chain=(),
        channels_with_seed=("__start__",),
    )
    assert "NULL::uuid AS checkpoint_id" in sql_aio
    assert "NULL::text AS checkpoint_id" not in sql_aio


# ---------------------------------------------------------------------------
# Unit-2: patch é no-op em lib já corrigida
# ---------------------------------------------------------------------------


def test_install_postgres_uuid_patch_is_noop_when_lib_already_fixed(
    restore_patch: Any,
) -> None:
    """Unit-2 (REQ-001 cenário "Patch é no-op em lib já corrigida").

    Given: a lib upstream já gera `NULL::uuid AS checkpoint_id` no
    branch "b" (i.e. o bug está corrigido).

    When: `install_postgres_uuid_patch()` é chamado.

    Then: a função instalada no módulo NÃO é substituída — a referência
    original é preservada.

    Estratégia: monkeypatch a função original do módulo para uma
    versão "já corrigida" antes de chamar `install_postgres_uuid_patch`,
    garantindo a pré-condição independentemente da versão da lib
    instalada no ambiente.
    """
    original_fn = restore_patch

    # Substitui temporariamente a função original por uma "já corrigida"
    # para simular uma lib sem bug.

    def already_fixed_fn(
        *,
        channels_with_chain: tuple[str, ...],
        channels_with_seed: tuple[str, ...],
    ) -> str:
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
                "SELECT 'b'::text AS _kind, NULL::uuid AS checkpoint_id, channel, "
                "type, blob, NULL::uuid AS task_id, NULL::int AS idx, version "
                "FROM checkpoint_blobs "
                "WHERE thread_id = %s AND checkpoint_ns = %s AND channel = %s "
                "AND version = %s"
            )
        return " UNION ALL ".join(branches)

    # Sanity check: a função "já corrigida" tem NULL::uuid.
    sql_already_fixed = already_fixed_fn(
        channels_with_chain=(), channels_with_seed=("__start__",)
    )
    assert "NULL::uuid AS checkpoint_id" in sql_already_fixed

    # Instala a versão "já corrigida" no módulo.
    lgcp_base._build_delta_stage2_sql = already_fixed_fn
    # Reimporta o patch module (que pode ter cached a referência da
    # função original) e garante que a função é vista como
    # "já corrigida".
    importlib.reload(patch_mod)

    # Aplica o patch — deve ser no-op.
    patch_mod.install_postgres_uuid_patch()

    # A função instalada no módulo deve ser EXATAMENTE a "já corrigida"
    # (mesma referência).
    assert lgcp_base._build_delta_stage2_sql is already_fixed_fn, (
        "Patch substituiu a função mesmo em lib já corrigida — deveria "
        "ser no-op"
    )


# ---------------------------------------------------------------------------
# Unit-3: patch é idempotente
# ---------------------------------------------------------------------------


def test_install_postgres_uuid_patch_is_idempotent(
    restore_patch: Any,
) -> None:
    """Unit-3 (REQ-001 cenário "Patch idempotente").

    Given: a lib tem o bug (caso do unit-1).

    When: `install_postgres_uuid_patch()` é chamado duas vezes
    seguidas.

    Then: a segunda chamada NÃO levanta exceção, NÃO sobrescreve a
    função patchada com uma cópia diferente, e a SQL final gerada
    permanece a mesma.

    Verificação: capturar a referência da função após o 1º call,
    chamar o patch de novo, e confirmar que a referência é a mesma
    (i.e. o patch detectou que já estava aplicado e virou no-op).
    """
    original_fn = restore_patch

    # Sanity check (lib tem o bug):
    sql_with_bug = original_fn(
        channels_with_chain=("messages",),
        channels_with_seed=("__start__",),
    )
    if "NULL::uuid AS checkpoint_id" in sql_with_bug:
        pytest.skip(
            "lib upstream já consertou o bug — unit-3 não se aplica "
            "(patch seria no-op no 1º call, sem mudar a função)"
        )

    # 1ª chamada: aplica o patch.
    patch_mod.install_postgres_uuid_patch()
    fn_after_first_call = lgcp_base._build_delta_stage2_sql

    # 2ª chamada: deve ser no-op.
    patch_mod.install_postgres_uuid_patch()
    fn_after_second_call = lgcp_base._build_delta_stage2_sql

    # Mesma referência (não sobrescrita).
    assert fn_after_first_call is fn_after_second_call, (
        "2ª chamada de install_postgres_uuid_patch() sobrescreveu a "
        "função com uma nova cópia — esperado no-op (mesma referência)"
    )

    # SQL gerada continua com NULL::uuid.
    sql = fn_after_second_call(
        channels_with_chain=(),
        channels_with_seed=("__start__",),
    )
    assert "NULL::uuid AS checkpoint_id" in sql
    assert "NULL::text AS checkpoint_id" not in sql


# ---------------------------------------------------------------------------
# Unit-4: a SQL gerada é executável (cobre REQ-002)
# ---------------------------------------------------------------------------


def test_patched_sql_is_well_formed_union(
    restore_patch: Any,
) -> None:
    """Unit-4 (REQ-002 cenário "SQL com a UNION modificada roda sem DatatypeMismatch").

    Given: o patch está instalado e a lib tem o bug (caso do unit-1).

    When: a função patchada é chamada com pelo menos 1 chain e 1 seed
    channel (para garantir que AMBOS os branches sejam gerados).

    Then: a SQL resultante tem EXATAMENTE 2 branches ("w" e "b"),
    separados por " UNION ALL ", e o branch "b" usa `NULL::uuid` (não
    `NULL::text`) para `checkpoint_id` e `task_id`. Validação por
    introspecção da string — sem precisar de Postgres real.
    """
    original_fn = restore_patch

    sql_with_bug = original_fn(
        channels_with_chain=("messages",),
        channels_with_seed=("__start__",),
    )
    if "NULL::uuid AS checkpoint_id" in sql_with_bug:
        pytest.skip(
            "lib upstream já consertou o bug — unit-4 não se aplica"
        )

    patch_mod.install_postgres_uuid_patch()

    sql = lgcp_base._build_delta_stage2_sql(
        channels_with_chain=("messages",), channels_with_seed=("__start__",)
    )

    # Estrutura esperada: 2 branches, " UNION ALL " entre eles.
    assert " UNION ALL " in sql, (
        f"SQL gerada não tem ' UNION ALL ': {sql!r}"
    )
    branches = sql.split(" UNION ALL ")
    assert len(branches) == 2, (
        f"Esperado 2 branches, encontrado {len(branches)}: {sql!r}"
    )

    w_branch, b_branch = branches
    # Branch "w" deve selecionar `checkpoint_id` direto da tabela
    # (que é `uuid`) e terminar com `NULL::text AS version` (a
    # versão só existe em checkpoint_blobs).
    assert "FROM checkpoint_writes" in w_branch
    assert "'w'::text AS _kind" in w_branch
    assert "NULL::text AS version" in w_branch
    # Branch "b" deve selecionar `NULL::uuid` para as colunas que
    # são uuid no schema.
    assert "FROM checkpoint_blobs" in b_branch
    assert "'b'::text AS _kind" in b_branch
    assert "NULL::uuid AS checkpoint_id" in b_branch
    assert "NULL::uuid AS task_id" in b_branch
    # E NÃO `NULL::text` para essas duas colunas no branch "b".
    assert "NULL::text AS checkpoint_id" not in b_branch
    assert "NULL::text AS task_id" not in b_branch
