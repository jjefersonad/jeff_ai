"""Caso de uso: criar uma tarefa agendada.

Recebe as portas `ScheduledTaskRepositoryPort` e `TaskSchedulerPort` por
injeção de dependência, monta a entidade `ScheduledTask` (validação fica
na entidade) e dispara os dois efeitos colaterais: persistência + registro
do trigger. Cobre o REQ-003 do spec `task-scheduling`.
"""
from __future__ import annotations

from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.application.ports.task_scheduler import TaskSchedulerPort
from src.domain.scheduling import Schedule, ScheduledTask, ToolScope


class CreateScheduledTask:
    """Orquestra a criação de uma `ScheduledTask` (persistência + agendamento).

    Depende apenas das portas; não conhece Postgres, APScheduler nem
    qualquer adapter concreto. O caller (tool Tier 2 ou o `jeff_cli.py`)
    monta esta classe com os adapters injetados em runtime.
    """

    def __init__(
        self,
        *,
        repository: ScheduledTaskRepositoryPort,
        scheduler: TaskSchedulerPort,
    ) -> None:
        """Recebe as implementações das portas por injeção de dependência."""
        self._repository = repository
        self._scheduler = scheduler

    async def execute(
        self,
        *,
        task_id: str,
        prompt: str,
        thread_id: str,
        schedule: Schedule,
        tool_scope: ToolScope = ToolScope.RESTRICTED,
        skills: tuple[str, ...] = (),
        created_by: str | None = None,
        timeout_seconds: int | None = None,
    ) -> ScheduledTask:
        """Monta a entidade, persiste e agenda o gatilho (REQ-003).

        Args:
            task_id: Identificador único (chave primária em `scheduled_tasks`).
            prompt: Mensagem que o agente vai receber quando a tarefa disparar.
            thread_id: Thread de destino (checkpointing compartilha com chat).
            schedule: Quando a tarefa deve rodar (once/cron).
            tool_scope: Escopo de tools (RESTRICTED default, FULL se pedir).
            skills: Skills extras a injetar (vazio = sem skills extras).
            created_by: Texto livre para auditoria (sem FK nesta change).
            timeout_seconds: Se None, usa o default da entidade (300s).

        Returns:
            A `ScheduledTask` persistida, em status SCHEDULED.

        Raises:
            DomainError: Se algum campo da entidade for inválido.
        """
        # Monta kwargs opcionais só quando fornecidos — assim o default da
        # entidade (`timeout_seconds=DEFAULT_TIMEOUT_SECONDS`) é respeitado
        # sem precisar conhecê-lo aqui.
        kwargs: dict[str, object] = {
            "id": task_id,
            "prompt": prompt,
            "thread_id": thread_id,
            "schedule": schedule,
            "tool_scope": tool_scope,
            "skills": skills,
            "created_by": created_by,
        }
        if timeout_seconds is not None:
            kwargs["timeout_seconds"] = timeout_seconds

        task = ScheduledTask(**kwargs)  # type: ignore[arg-type]

        # Persistência e agendamento: a ordem importa. Persistimos primeiro
        # para que, se o scheduler falhar, o retry possa re-agendar a partir
        # do banco (ver design, REQ-001 + REQ-005).
        await self._repository.save(task)
        await self._scheduler.schedule(task)
        return task
