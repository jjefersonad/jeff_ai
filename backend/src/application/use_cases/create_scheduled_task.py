"""Caso de uso: criar uma tarefa agendada.

Recebe as portas `ScheduledTaskRepositoryPort` e `TaskSchedulerPort` por
injeção de dependência, monta a entidade `ScheduledTask` (validação fica
na entidade) e dispara os dois efeitos colaterais: persistência + registro
do trigger. Cobre o REQ-003 do spec `task-scheduling`.

`delivery_channel` (scheduled-channel-routines): resolvido via
`ResolveDeliveryTarget` **antes** de persistir/agendar — sem vínculo não
deixa trigger órfão (REQ-002 targeting).
"""
from __future__ import annotations

from typing import Protocol

from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.application.ports.task_scheduler import TaskSchedulerPort
from src.domain.scheduling import Schedule, ScheduledTask, ToolScope
from src.domain.shared.errors import DomainError


class DeliveryTargetResolver(Protocol):
    """Contrato mínimo de `ResolveDeliveryTarget.resolve` (testável com fake)."""

    async def resolve(
        self, *, user_id: str, delivery_channel: str | None
    ) -> str | None: ...


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
        delivery_resolver: DeliveryTargetResolver,
    ) -> None:
        """Recebe as implementações das portas por injeção de dependência."""
        self._repository = repository
        self._scheduler = scheduler
        self._delivery_resolver = delivery_resolver

    async def execute(
        self,
        *,
        task_id: str,
        prompt: str,
        thread_id: str,
        schedule: Schedule,
        tool_scope: ToolScope = ToolScope.RESTRICTED,
        skills: tuple[str, ...] = (),
        owner_user_key: str | None = None,
        owner_user_id: str | None = None,
        delivery_channel: str | None = None,
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
            owner_user_key: Identidade do dono (`web:<uuid>` / `telegram:<chat_id>`),
                sem FK — mesma convenção usada pela listagem/cancelamento/edição.
                Sempre da sessão/caller — nunca derivado de `delivery_channel`.
            owner_user_id: UUID canônico do owner (necessário se
                `delivery_channel` for informado).
            delivery_channel: Canal de entrega opcional (`web`/`telegram`/
                `whatsapp`); omitido → `delivery_user_key=None`.
            timeout_seconds: Se None, usa o default da entidade (300s).

        Returns:
            A `ScheduledTask` persistida, em status SCHEDULED.

        Raises:
            DomainError: Se algum campo da entidade for inválido, ou se o
                destino de entrega não puder ser resolvido.
        """
        delivery_user_key = await self._resolve_delivery(
            owner_user_id=owner_user_id,
            delivery_channel=delivery_channel,
        )

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
            "owner_user_key": owner_user_key,
            "delivery_user_key": delivery_user_key,
        }
        if timeout_seconds is not None:
            kwargs["timeout_seconds"] = timeout_seconds

        task = ScheduledTask(**kwargs)  # type: ignore[arg-type]

        # Persistência e agendamento: a ordem importa. Persistimos primeiro
        # para que, se o scheduler falhar, o retry possa re-agendar a partir
        # do banco (ver design, REQ-001 + REQ-005). Resolução de delivery
        # acontece ANTES — falha de vínculo não deixa linha/trigger órfão.
        await self._repository.save(task)
        await self._scheduler.schedule(task)
        return task

    async def _resolve_delivery(
        self,
        *,
        owner_user_id: str | None,
        delivery_channel: str | None,
    ) -> str | None:
        if delivery_channel is None:
            return None
        if not owner_user_id:
            raise DomainError(
                "delivery_channel exige owner_user_id do caller autenticado"
            )
        return await self._delivery_resolver.resolve(
            user_id=owner_user_id,
            delivery_channel=delivery_channel,
        )
