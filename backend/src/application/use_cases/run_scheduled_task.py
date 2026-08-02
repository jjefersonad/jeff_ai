"""Caso de uso: executar uma tarefa agendada (disparada pelo scheduler).

Recebe `ScheduledTaskRepositoryPort` e `AgentRunnerPort` por injeção de
dependência, aplica a máquina de estado da entidade em torno da chamada ao
agente e persiste o resultado. Cobre REQ-002, REQ-006, REQ-007 e REQ-008 do
spec `task-scheduling`.
"""
from __future__ import annotations

import asyncio

from src.application.ports.agent_runner import AgentRunnerPort
from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort


class RunScheduledTask:
    """Orquestra uma execução isolada de `ScheduledTask` (repo + agent runner).

    Depende apenas das portas; não conhece Postgres, APScheduler nem o
    grafo `unified`. O caller (`jeff_cli.py`) monta esta classe com os
    adapters injetados em runtime.
    """

    def __init__(
        self,
        *,
        repository: ScheduledTaskRepositoryPort,
        agent_runner: AgentRunnerPort,
    ) -> None:
        """Recebe as implementações das portas por injeção de dependência."""
        self._repository = repository
        self._agent_runner = agent_runner

    async def execute(self, *, task_id: str) -> None:
        """Busca, executa e finaliza a tarefa `task_id` (REQ-002/006/007/008).

        Args:
            task_id: Identificador da tarefa a executar.

        Tarefa inexistente (cancelada entre agendamento e disparo) é um
        caso esperado — não levanta exceção.
        """
        task = await self._repository.get(task_id)
        if task is None:
            return

        task.start()
        try:
            result = await asyncio.wait_for(
                self._agent_runner.run(
                    thread_id=task.thread_id,
                    prompt=task.prompt,
                    skills=task.skills,
                    tool_scope=task.tool_scope,
                    user_key=task.owner_user_key,
                ),
                timeout=task.timeout_seconds,
            )
        except TimeoutError:
            task.fail(
                f"Execução excedeu o timeout de {task.timeout_seconds}s."
            )
        except Exception as exc:  # noqa: BLE001 - qualquer falha do agente vira FAILED
            task.fail(str(exc))
        else:
            if result.status == "ok":
                task.succeed()
            else:
                task.fail(result.error or f"Agente retornou status={result.status!r}.")

        await self._repository.save(task)
