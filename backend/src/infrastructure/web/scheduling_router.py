"""Rotas REST de `ScheduledTask` (`GET`/`POST`/`PATCH`/`DELETE /api/scheduled-tasks`).

Mesmo molde de `usage_router.py`: dependency-factory `_scheduled_task_repository()`
constrói `PostgresScheduledTaskRepository` por requisição a partir de
`POSTGRES_URI`; o scheduler reusa o singleton do processo
(`scheduler_instance.task_scheduler`). `is_admin`/`owner_user_key` são
resolvidos do `User` de `require_auth` — nunca de um campo do corpo da
requisição (REQ-005 do spec `scheduled-tasks-rest-api`).
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.application.ports.task_scheduler import TaskSchedulerPort
from src.application.use_cases.cancel_scheduled_task import (
    CancelScheduledTask,
    ScheduledTaskAuthorizationError,
)
from src.application.use_cases.create_scheduled_task import CreateScheduledTask
from src.application.use_cases.list_scheduled_tasks import ListScheduledTasks
from src.application.use_cases.update_scheduled_task import (
    ScheduledTaskNotEditableError,
    UpdateScheduledTask,
)
from src.domain.scheduling import Schedule, ScheduledTask, ToolScope
from src.domain.shared.errors import DomainError
from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.users import User
from src.infrastructure.persistence.scheduled_task_repository import (
    PostgresScheduledTaskRepository,
)
from src.infrastructure.scheduling.scheduler_instance import task_scheduler

router = APIRouter()


def _scheduled_task_repository() -> ScheduledTaskRepositoryPort:
    """Constrói o repositório a partir de `POSTGRES_URI`."""
    return PostgresScheduledTaskRepository(os.environ["POSTGRES_URI"])


def _task_scheduler_dependency() -> TaskSchedulerPort:
    """Reusa o singleton `task_scheduler` do processo (ver `scheduler_instance.py`)."""
    return task_scheduler


class ScheduledTaskCreateRequest(BaseModel):
    """Corpo de `POST /api/scheduled-tasks`. Nenhum campo de ownership."""

    prompt: str
    schedule_kind: str
    schedule_expr: str
    tool_scope: str = "restricted"
    skills: list[str] = []
    timeout_seconds: int | None = None


class ScheduledTaskUpdateRequest(BaseModel):
    """Corpo de `PATCH /api/scheduled-tasks/{id}`. Todos os campos opcionais.

    `schedule_kind`/`schedule_expr` devem ser fornecidos juntos (ou nenhum
    dos dois) — não faz sentido trocar só o tipo ou só a expressão do
    schedule. Nenhum campo de ownership.
    """

    prompt: str | None = None
    schedule_kind: str | None = None
    schedule_expr: str | None = None
    tool_scope: str | None = None
    skills: list[str] | None = None


class ScheduledTaskResponse(BaseModel):
    """Contrato HTTP de uma `ScheduledTask` — não expõe a entidade de domínio direto."""

    id: str
    prompt: str
    thread_id: str
    schedule_kind: str
    schedule_expr: str
    tool_scope: str
    skills: list[str]
    timeout_seconds: int
    status: str
    owner_user_key: str
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    created_at: datetime


def _to_response(task: ScheduledTask) -> ScheduledTaskResponse:
    return ScheduledTaskResponse(
        id=task.id,
        prompt=task.prompt,
        thread_id=task.thread_id,
        schedule_kind=task.schedule.kind,
        schedule_expr=task.schedule.expr,
        tool_scope=task.tool_scope.value,
        skills=list(task.skills),
        timeout_seconds=task.timeout_seconds,
        status=task.status.value,
        owner_user_key=task.owner_user_key,
        started_at=task.started_at,
        finished_at=task.finished_at,
        error=task.error,
        created_at=task.created_at,
    )


@router.get("/api/scheduled-tasks")
async def list_scheduled_tasks_endpoint(
    user: User | None = Depends(require_auth),
    repo: ScheduledTaskRepositoryPort = Depends(_scheduled_task_repository),
) -> list[ScheduledTaskResponse]:
    """REQ-001: escopado ao dono, exceto `role=admin` (todas as tarefas)."""
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    use_case = ListScheduledTasks(repository=repo)
    tasks = await use_case.execute(
        caller_user_key=f"web:{user.id}", is_admin=user.role == "admin"
    )
    return [_to_response(t) for t in tasks]


@router.post("/api/scheduled-tasks", status_code=201)
async def create_scheduled_task_endpoint(
    body: ScheduledTaskCreateRequest,
    user: User | None = Depends(require_auth),
    repo: ScheduledTaskRepositoryPort = Depends(_scheduled_task_repository),
    scheduler: TaskSchedulerPort = Depends(_task_scheduler_dependency),
) -> ScheduledTaskResponse:
    """REQ-002: `owner_user_key` sempre resolvido da sessão, nunca do corpo."""
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        schedule = Schedule(kind=body.schedule_kind, expr=body.schedule_expr)
        scope = ToolScope(body.tool_scope)
    except (DomainError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    use_case = CreateScheduledTask(repository=repo, scheduler=scheduler)
    try:
        task = await use_case.execute(
            task_id=uuid.uuid4().hex,
            prompt=body.prompt,
            thread_id=uuid.uuid4().hex,
            schedule=schedule,
            owner_user_key=f"web:{user.id}",
            tool_scope=scope,
            skills=tuple(body.skills),
            timeout_seconds=body.timeout_seconds,
        )
    except DomainError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(task)


@router.patch("/api/scheduled-tasks/{task_id}")
async def update_scheduled_task_endpoint(
    task_id: str,
    body: ScheduledTaskUpdateRequest,
    user: User | None = Depends(require_auth),
    repo: ScheduledTaskRepositoryPort = Depends(_scheduled_task_repository),
    scheduler: TaskSchedulerPort = Depends(_task_scheduler_dependency),
) -> ScheduledTaskResponse:
    """REQ-003: edição restrita a `SCHEDULED`; REQ-005: autorização da sessão."""
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if (body.schedule_kind is None) != (body.schedule_expr is None):
        raise HTTPException(
            status_code=422,
            detail="schedule_kind e schedule_expr devem ser fornecidos juntos.",
        )

    try:
        schedule = (
            Schedule(kind=body.schedule_kind, expr=body.schedule_expr)
            if body.schedule_kind is not None and body.schedule_expr is not None
            else None
        )
        tool_scope = ToolScope(body.tool_scope) if body.tool_scope is not None else None
    except (DomainError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    use_case = UpdateScheduledTask(repository=repo, scheduler=scheduler)
    try:
        task = await use_case.execute(
            task_id=task_id,
            caller_user_key=f"web:{user.id}",
            is_admin=user.role == "admin",
            prompt=body.prompt,
            schedule=schedule,
            tool_scope=tool_scope,
            skills=tuple(body.skills) if body.skills is not None else None,
        )
    except ScheduledTaskAuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ScheduledTaskNotEditableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if task is None:
        raise HTTPException(status_code=404, detail="Scheduled task not found")

    return _to_response(task)


@router.delete(
    "/api/scheduled-tasks/{task_id}",
    status_code=204,
    response_class=Response,
    response_model=None,
)
async def cancel_scheduled_task_endpoint(
    task_id: str,
    user: User | None = Depends(require_auth),
    repo: ScheduledTaskRepositoryPort = Depends(_scheduled_task_repository),
    scheduler: TaskSchedulerPort = Depends(_task_scheduler_dependency),
) -> Response:
    """REQ-004: exclusão via `CancelScheduledTask`; REQ-005: autorização da sessão."""
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    use_case = CancelScheduledTask(repository=repo, scheduler=scheduler)
    try:
        await use_case.execute(
            task_id=task_id,
            caller_user_key=f"web:{user.id}",
            is_admin=user.role == "admin",
        )
    except ScheduledTaskAuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return Response(status_code=204)
