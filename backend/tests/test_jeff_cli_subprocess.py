"""Teste de processo: `jeff_cli.py` como subprocesso real (task
`agendamento-jeff-cli-task-runtime-2`).

Cobre o critério de aceite:
> Teste de processo: subprocesso real com job_id fixo, confere exit code e
> efeito no banco (status atualizado)

Usa `timeout_seconds` bem curto na tarefa para que o teste seja
determinístico independente de o LLM real (Ollama/OpenRouter, configurado
em `src/agents/unified/agent.py`) estar acessível neste ambiente: ou a
chamada falha rápido (rede indisponível) ou estoura o timeout — em ambos os
casos `RunScheduledTask` marca a tarefa FAILED e o subprocesso sai com
código != 0 (jeff-cli REQ-004). O teste não afirma nada sobre o conteúdo do
erro, só que o pipeline completo (subprocesso → composition root →
Postgres) roda de ponta a ponta e grava o efeito esperado no banco.

Requer `INTEGRATION_POSTGRES_URI` apontando para um Postgres real — mesmo
padrão de `test_scheduled_task_repository.py`.
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from src.domain.scheduling import Schedule, ScheduledTask, TaskStatus
from src.infrastructure.persistence.scheduled_task_repository import (
    PostgresScheduledTaskRepository,
)
from src.infrastructure.persistence.scheduled_tasks_schema import ensure_schema

INTEGRATION_URI_ENV = "INTEGRATION_POSTGRES_URI"
pytestmark = pytest.mark.skipif(
    not os.environ.get(INTEGRATION_URI_ENV),
    reason=(
        f"Requer Postgres de teste real. Defina {INTEGRATION_URI_ENV} "
        "(ex.: postgresql://jeff_ia:jeff_ia@localhost:5436/jeff_ia) "
        "para rodar este teste."
    ),
)

_BACKEND_ROOT = Path(__file__).parent.parent


def _uri() -> str:
    return os.environ[INTEGRATION_URI_ENV]


async def test_jeff_cli_subprocess_runs_job_and_updates_task_status() -> None:
    ensure_schema(_uri())
    repo = PostgresScheduledTaskRepository(_uri())
    job_id = str(uuid.uuid4())
    task = ScheduledTask(
        id=job_id,
        prompt="diga oi",
        thread_id=f"th-{job_id}",
        schedule=Schedule(kind="once", expr="2026-01-01T00:00:00"),
        owner_user_key="web:owner-1",
        timeout_seconds=3,
    )
    await repo.save(task)

    env = {**os.environ, "POSTGRES_URI": _uri()}
    result = subprocess.run(
        [sys.executable, "-m", "src.infrastructure.cli.jeff_cli", "--job-id", job_id],
        cwd=str(_BACKEND_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    # jeff-cli REQ-004: != 0 porque a tarefa não termina SUCCEEDED (sem LLM
    # real disponível no ambiente de teste, ver docstring do módulo).
    assert result.returncode != 0, (
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )

    stored = await repo.get(job_id)
    assert stored is not None
    assert stored.status == TaskStatus.FAILED
    assert stored.error is not None
