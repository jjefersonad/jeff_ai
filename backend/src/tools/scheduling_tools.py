"""Tools de agendamento: `create_scheduled_task`, `list_scheduled_tasks`, `cancel_scheduled_task`.

Controllers finos sobre os use cases de
`application/use_cases/{create,list,cancel}_scheduled_task.py` (spec
`task-scheduling`, REQ-003/REQ-004/REQ-008).

Toda regra de negócio (máquina de estado, ownership, agendamento) vive nos
use cases e no domínio; aqui só há tradução de argumentos + resolução de
identidade + chamada ao use case.

`owner_user_key`/`caller_user_key` são resolvidos de
`get_config().get("configurable", {}).get("user_key")` — mesmo padrão de
`_current_thread_id()` em `style_memory_tools.py` — NUNCA aceitos como
parâmetro de tool-call: impossível de "spoofar" via argumento do agente.

`is_admin` (REQ-004/REQ-008) é resolvido via `ownership.store.resolve_user_id()`
(task `user-integration-credentials-task-resolve-2`), o mesmo resolvedor
canônico usado por `mcp_tools_middleware` e pelas tools de memória — tanto
sessões web (`web:<uuid>`) quanto sessões Telegram com vínculo ativo em
`user_integrations` (`telegram:<chat_id>`) agora consultam `role` via
`get_user_by_id`.
"""
from __future__ import annotations

import uuid
from typing import Any

from langchain_core.tools import tool
from langgraph.config import get_config

from src.application.use_cases.cancel_scheduled_task import (
    ScheduledTaskAuthorizationError,
)
from src.composition.dependencies import (
    build_cancel_scheduled_task,
    build_create_scheduled_task,
    build_list_scheduled_tasks,
)
from src.domain.scheduling import Schedule, ScheduledTask, ToolScope
from src.domain.shared.errors import DomainError
from src.infrastructure.auth.users import get_user_by_id
from src.infrastructure.ownership.store import resolve_user_id


def _configurable() -> dict[str, Any]:
    return get_config().get("configurable", {})


def _current_user_key() -> str | None:
    return _configurable().get("user_key")


def _current_thread_id() -> str:
    return _configurable().get("thread_id", "default_thread")


async def _resolve_caller_identity() -> tuple[str | None, bool]:
    """Resolve (caller_user_key, is_admin) do configurable do run atual (REQ-004/REQ-008).

    `caller_user_key` continua o `user_key` bruto (`web:<uuid>` ou
    `telegram:<chat_id>`) — é o que a ownership de `ScheduledTask` usa para
    comparar com `owner_user_key`. `is_admin` é resolvido via
    `resolve_user_id()`: tanto sessões web quanto sessões Telegram com
    vínculo ativo em `user_integrations` consultam `role` via
    `get_user_by_id`; sem `user_id` resolvível, `is_admin=False`.
    """
    user_key = _current_user_key()
    user_id = await resolve_user_id()
    is_admin = False
    if user_id is not None:
        user = await get_user_by_id(user_id)
        is_admin = bool(user and user.role == "admin")
    return user_key, is_admin


def _task_to_dict(task: ScheduledTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "prompt": task.prompt,
        "thread_id": task.thread_id,
        "schedule": {"kind": task.schedule.kind, "expr": task.schedule.expr},
        "tool_scope": task.tool_scope.value,
        "skills": list(task.skills),
        "timeout_seconds": task.timeout_seconds,
        "status": task.status.value,
        "owner_user_key": task.owner_user_key,
        "delivery_user_key": task.delivery_user_key,
        "effective_delivery_user_key": task.effective_delivery_user_key,
        "notify_status": task.notify_status,
        "notify_error": task.notify_error,
        "profile_id": task.profile_id,
    }


@tool
async def create_scheduled_task(
    prompt: str,
    schedule_kind: str,
    schedule_expr: str,
    tool_scope: str = "restricted",
    skills: list[str] | None = None,
    timeout_seconds: int | None = None,
    delivery_channel: str | None = None,
    profile_id: str | None = None,
) -> dict[str, Any]:
    """Agenda uma tarefa para o agente rodar no futuro, uma vez ou de forma recorrente.

    `schedule_kind`: "once" (dispara uma vez em `schedule_expr`, data ISO 8601,
    ex. "2026-12-31T23:59:00") ou "cron" (recorrente; `schedule_expr` com 5
    campos "min hora dia mês dia-da-semana", ex. "0 9 * * *" = todo dia às 9h).
    `tool_scope`: "restricted" (default — só tools Tier 1/2, seguro para rodar
    sem supervisão) ou "full" (todas as tools; qualquer Tier 3/4 pausa
    aguardando aprovação humana, igual a uma conversa normal).
    `delivery_channel` (opcional): canal de notificação/HITL — `"web"`,
    `"telegram"` ou `"whatsapp"`, resolvido contra os vínculos do usuário
    autenticado. Omitido → notifica no canal da sessão (na web isso NÃO
    chega no WhatsApp). Se o usuário pediu entrega em WhatsApp/Telegram
    a partir de outra sessão, passe o canal explicitamente
    (`delivery_channel="whatsapp"` etc.). O texto notificado é a
    resposta final do agente ao `prompt` — não instrua o prompt a chamar
    `send_message`. NÃO aceite identificadores crus de terceiros.
    `profile_id` (opcional): UUID de um `AgentProfile` ativo do próprio
    usuário. Omitido herda `configurable.profile_id` da sessão; sem
    sessão e sem argumento, grava `null` (overlay no-op). Não é possível
    agendar com o perfil de outro usuário. A tarefa roda na MESMA thread
    desta conversa e pertence a QUEM está conversando agora — não é
    possível agendar em nome de outro usuário (`owner_user_key` não é
    parâmetro desta tool).
    """
    owner_user_key = _current_user_key()
    if not owner_user_key:
        return {
            "error": "Identidade do usuário não resolvida para esta sessão; "
            "não é possível criar a tarefa."
        }
    try:
        schedule = Schedule(kind=schedule_kind, expr=schedule_expr)
        scope = ToolScope(tool_scope)
    except (DomainError, ValueError) as exc:
        return {"error": str(exc)}

    owner_user_id = await resolve_user_id()
    use_case = build_create_scheduled_task()
    try:
        task = await use_case.execute(
            task_id=uuid.uuid4().hex,
            prompt=prompt,
            thread_id=_current_thread_id(),
            schedule=schedule,
            owner_user_key=owner_user_key,
            owner_user_id=owner_user_id,
            delivery_channel=delivery_channel,
            tool_scope=scope,
            skills=tuple(skills or ()),
            timeout_seconds=timeout_seconds,
            profile_id=profile_id,
            session_profile_id=_configurable().get("profile_id"),
        )
    except DomainError as exc:
        return {"error": str(exc)}
    return _task_to_dict(task)


@tool
async def list_scheduled_tasks() -> list[dict[str, Any]] | dict[str, Any]:
    """Lista as tarefas agendadas do usuário atual (todas as tarefas, se `role=admin`)."""
    caller_user_key, is_admin = await _resolve_caller_identity()
    if not caller_user_key:
        return {"error": "Identidade do usuário não resolvida para esta sessão."}
    use_case = build_list_scheduled_tasks()
    tasks = await use_case.execute(caller_user_key=caller_user_key, is_admin=is_admin)
    return [_task_to_dict(t) for t in tasks]


@tool
async def cancel_scheduled_task(task_id: str) -> dict[str, Any]:
    """Cancela uma tarefa agendada pelo `id` (dono da tarefa ou `role=admin`).

    Tentar cancelar a tarefa de outro usuário sem ser admin devolve um erro
    explicativo — a tarefa NÃO é removida. Um `task_id` inexistente é
    tolerado (nenhum efeito, sem erro).
    """
    caller_user_key, is_admin = await _resolve_caller_identity()
    if not caller_user_key:
        return {"error": "Identidade do usuário não resolvida para esta sessão."}
    use_case = build_cancel_scheduled_task()
    try:
        await use_case.execute(
            task_id=task_id, caller_user_key=caller_user_key, is_admin=is_admin
        )
    except ScheduledTaskAuthorizationError as exc:
        return {"error": str(exc)}
    return {"success": True, "task_id": task_id}
