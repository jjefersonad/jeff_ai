"""Testes dos use cases `ListScheduledTasks` e `CancelScheduledTask`
(task `agendamento-jeff-cli-task-application-3`).

Puro: usa fakes das portas. Cobre REQ-004 e REQ-008 do spec `task-scheduling`:

- REQ-004 — listagem escopada por `caller_user_key` (não-admin vê só as
  próprias; admin vê todas).
- REQ-004 — cancelamento: dono OU admin remove; não-dono não-admin recebe
  erro de autorização; tarefa inexistente é no-op tolerante.
- REQ-008 — `CancelScheduledTask` levanta `ScheduledTaskAuthorizationError`
  novo, distinto do "não encontrado".
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.application.ports.task_scheduler import TaskSchedulerPort
from src.application.use_cases.cancel_scheduled_task import (
    CancelScheduledTask,
    ScheduledTaskAuthorizationError,
)
from src.application.use_cases.list_scheduled_tasks import ListScheduledTasks
from src.domain.scheduling import (
    Schedule,
    ScheduledTask,
)

# ---------------------------------------------------------------------------
# Fakes locais (reutilizam o mesmo padrão de test_create_scheduled_task.py)
# ---------------------------------------------------------------------------


class _FakeRepository(ScheduledTaskRepositoryPort):
    def __init__(self) -> None:
        self._store: dict[str, ScheduledTask] = {}
        # Contadores para distinguir os caminhos
        self.delete_calls: list[str] = []

    async def save(self, task: ScheduledTask) -> None:
        self._store[task.id] = task

    async def get(self, task_id: str) -> ScheduledTask | None:
        return self._store.get(task_id)

    async def list_all(self) -> list[ScheduledTask]:
        return list(self._store.values())

    async def list_by_owner(self, owner_user_key: str) -> list[ScheduledTask]:
        return [t for t in self._store.values() if t.owner_user_key == owner_user_key]

    async def delete(self, task_id: str) -> None:
        self.delete_calls.append(task_id)
        self._store.pop(task_id, None)


class _FakeScheduler(TaskSchedulerPort):
    def __init__(self) -> None:
        self.scheduled: list[str] = []
        self.unscheduled: list[str] = []

    async def schedule(self, task: ScheduledTask) -> None:
        self.scheduled.append(task.id)

    async def unschedule(self, task_id: str) -> None:
        self.unscheduled.append(task_id)


def _make_task(
    *,
    id_: str,
    owner: str,
    prompt: str = "x",
    thread_id: str = "th-1",
) -> ScheduledTask:
    """Helper para criar tarefa válida sem repetir boilerplate."""
    return ScheduledTask(
        id=id_,
        prompt=prompt,
        thread_id=thread_id,
        schedule=Schedule(kind="once", expr="2026-12-31T23:59:00"),
        owner_user_key=owner,
    )


# ===========================================================================
# ListScheduledTasks — REQ-004
# ===========================================================================


@pytest.mark.asyncio
async def test_list_returns_only_callers_tasks_when_not_admin():
    """Usuário não-admin vê só as próprias tarefas (REQ-004 cenário "Usuário lista")."""
    repo = _FakeRepository()
    await repo.save(_make_task(id_="t-a", owner="web:user-a"))
    await repo.save(_make_task(id_="t-b", owner="web:user-b"))
    await repo.save(_make_task(id_="t-c", owner="telegram:42"))

    use_case = ListScheduledTasks(repository=repo)
    result = await use_case.execute(caller_user_key="web:user-a", is_admin=False)

    ids = sorted(t.id for t in result)
    assert ids == ["t-a"]


@pytest.mark.asyncio
async def test_list_returns_all_tasks_when_admin():
    """Admin vê TODAS as tarefas independente de owner (REQ-004 cenário "Admin lista")."""
    repo = _FakeRepository()
    await repo.save(_make_task(id_="t-a", owner="web:user-a"))
    await repo.save(_make_task(id_="t-b", owner="web:user-b"))
    await repo.save(_make_task(id_="t-c", owner="telegram:42"))

    use_case = ListScheduledTasks(repository=repo)
    result = await use_case.execute(caller_user_key="web:admin-x", is_admin=True)

    ids = sorted(t.id for t in result)
    assert ids == ["t-a", "t-b", "t-c"]


@pytest.mark.asyncio
async def test_list_returns_empty_list_when_callers_owner_has_no_tasks():
    """Não-admin sem tarefas: lista vazia, não erro."""
    repo = _FakeRepository()
    await repo.save(_make_task(id_="t-other", owner="web:someone-else"))

    use_case = ListScheduledTasks(repository=repo)
    result = await use_case.execute(caller_user_key="web:me", is_admin=False)

    assert result == []


# ===========================================================================
# CancelScheduledTask — REQ-004 / REQ-008
# ===========================================================================


@pytest.mark.asyncio
async def test_cancel_removes_own_task_for_owner():
    """Dono cancela a própria tarefa: remove repo E desagenda."""
    repo = _FakeRepository()
    sched = _FakeScheduler()
    await repo.save(_make_task(id_="t-1", owner="web:user-a"))
    # Estado pré: tarefa existe
    assert await repo.get("t-1") is not None

    use_case = CancelScheduledTask(repository=repo, scheduler=sched)
    await use_case.execute(task_id="t-1", caller_user_key="web:user-a", is_admin=False)

    assert await repo.get("t-1") is None
    assert sched.unscheduled == ["t-1"]


@pytest.mark.asyncio
async def test_admin_cancels_another_users_task():
    """Admin cancela tarefa de outro usuário (bypass de ownership — REQ-004)."""
    repo = _FakeRepository()
    sched = _FakeScheduler()
    await repo.save(_make_task(id_="t-x", owner="web:user-b"))

    use_case = CancelScheduledTask(repository=repo, scheduler=sched)
    await use_case.execute(task_id="t-x", caller_user_key="web:admin", is_admin=True)

    assert await repo.get("t-x") is None
    assert sched.unscheduled == ["t-x"]


@pytest.mark.asyncio
async def test_non_admin_cancelling_others_task_raises_authorization_error():
    """Não-dono não-admin recebe erro de autorização e a tarefa NÃO é removida (REQ-008)."""
    repo = _FakeRepository()
    sched = _FakeScheduler()
    await repo.save(_make_task(id_="t-victim", owner="web:user-a"))

    use_case = CancelScheduledTask(repository=repo, scheduler=sched)

    with pytest.raises(ScheduledTaskAuthorizationError) as exc_info:
        await use_case.execute(
            task_id="t-victim", caller_user_key="web:user-b", is_admin=False
        )

    # Mensagem carrega contexto suficiente para o agente/tool reportar
    assert "t-victim" in str(exc_info.value)

    # Nada foi removido nem desagendado
    assert await repo.get("t-victim") is not None
    assert repo.delete_calls == []
    assert sched.unscheduled == []


@pytest.mark.asyncio
async def test_cancel_nonexistent_task_is_tolerated_noop():
    """`task_id` inexistente é no-op silencioso, distinto do caso de auth (REQ-008)."""
    repo = _FakeRepository()
    sched = _FakeScheduler()

    use_case = CancelScheduledTask(repository=repo, scheduler=sched)
    # NÃO deve levantar — diferente do caso de autorização negada
    await use_case.execute(
        task_id="t-does-not-exist", caller_user_key="web:user-a", is_admin=False
    )

    assert repo.delete_calls == ["t-does-not-exist"]  # tentativa de delete, sem efeito
    assert sched.unscheduled == []  # nada pra desagendar


@pytest.mark.asyncio
async def test_authorization_error_is_distinct_from_other_errors():
    """`ScheduledTaskAuthorizationError` é um tipo próprio (não reaproveita DomainError/ValueError)."""
    # Verificação estática: o tipo existe e é uma subclasse de Exception.
    assert issubclass(ScheduledTaskAuthorizationError, Exception)

    repo = _FakeRepository()
    sched = _FakeScheduler()
    await repo.save(_make_task(id_="t-z", owner="web:user-a"))

    use_case = CancelScheduledTask(repository=repo, scheduler=sched)
    with pytest.raises(ScheduledTaskAuthorizationError):
        await use_case.execute(
            task_id="t-z", caller_user_key="web:user-b", is_admin=False
        )


# ===========================================================================
# Injeção de dependência + guard estático contra framework concreto
# ===========================================================================


def test_list_constructor_stores_repository():
    repo = _FakeRepository()
    use_case = ListScheduledTasks(repository=repo)
    assert use_case._repository is repo


def test_cancel_constructor_stores_dependencies():
    repo = _FakeRepository()
    sched = _FakeScheduler()
    use_case = CancelScheduledTask(repository=repo, scheduler=sched)
    assert use_case._repository is repo
    assert use_case._scheduler is sched


@pytest.mark.parametrize(
    "filename",
    [
        "list_scheduled_tasks.py",
        "cancel_scheduled_task.py",
    ],
)
def test_use_case_modules_do_not_import_framework(filename: str):
    """Garantia estática: use cases de aplicação não importam infra concreta.

    Mesma convenção de `test_create_scheduled_task.py`.
    """
    src = (
        Path(__file__).parent.parent / "src" / "application" / "use_cases" / filename
    ).read_text()
    no_strings = re.sub(r'""".*?""""', "", src, flags=re.DOTALL)
    no_strings = re.sub(r"'''.*?'''", "", no_strings, flags=re.DOTALL)
    for forbidden in ("psycopg", "apscheduler", "langgraph", "fastapi"):
        assert not re.search(
            rf"^\s*(import|from)\s+{forbidden}\b", no_strings, flags=re.MULTILINE
        ), f"{filename} não pode importar {forbidden!r}"
