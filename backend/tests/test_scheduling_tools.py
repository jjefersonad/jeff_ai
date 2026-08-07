"""Testes de `src/tools/scheduling_tools.py` (task `agendamento-jeff-cli-task-tools-1`).

Cobre os critérios de aceite da task:
- REQ-003: `create_scheduled_task` resolve `owner_user_key` do `configurable`
  do run (nunca aceito como parâmetro) e roda direto (Tier 2).
- REQ-004/REQ-008: `list_scheduled_tasks`/`cancel_scheduled_task` resolvem
  `caller_user_key`/`is_admin` do mesmo `configurable`.
- `cancel_scheduled_task` traduz `ScheduledTaskAuthorizationError` numa
  mensagem clara (`{"error": ...}`), não uma stack trace crua.
- As 3 tools estão em `TIER_REGISTRY` como Tier 2 e em `_UNIFIED_TOOLS`.

Usa fakes das portas (mesmo padrão de `test_list_and_cancel_scheduled_tasks.py`)
e monkeypatcha `get_config`/`get_user_by_id`/os builders de composição — não
depende de Postgres nem de um runtime LangGraph ativo.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest

import src.tools.scheduling_tools as st
from src.agents.unified.effects import Capability
from src.application.ports.scheduled_task_repository import ScheduledTaskRepositoryPort
from src.application.ports.task_scheduler import TaskSchedulerPort
from src.application.use_cases.cancel_scheduled_task import CancelScheduledTask
from src.application.use_cases.create_scheduled_task import CreateScheduledTask
from src.application.use_cases.list_scheduled_tasks import ListScheduledTasks
from src.domain.scheduling import Schedule, ScheduledTask
from src.infrastructure.auth.users import User


_PLACEHOLDER_CREATED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _FakeRepository(ScheduledTaskRepositoryPort):
    def __init__(self) -> None:
        self._store: dict[str, ScheduledTask] = {}
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


def _configurable(monkeypatch: pytest.MonkeyPatch, **configurable: object) -> None:
    """Simula o `configurable` do run E o `resolve_user_id()` centralizado
    (task `resolve-2`) coerente com ele: `web:<uuid>` resolve o uuid; tudo o
    mais (incluindo `telegram:<chat_id>` sem vínculo simulado) resolve
    `None` — vínculo Telegram real é coberto por `_stub_resolved_user_id`."""
    monkeypatch.setattr(st, "get_config", lambda: {"configurable": configurable})
    user_key = configurable.get("user_key")
    resolved = (
        user_key.removeprefix("web:")
        if isinstance(user_key, str) and user_key.startswith("web:")
        else None
    )
    _stub_resolved_user_id(monkeypatch, resolved)


def _stub_resolved_user_id(monkeypatch: pytest.MonkeyPatch, user_id: str | None) -> None:
    """Simula `resolve_user_id()` retornando `user_id` diretamente — usado
    para representar uma sessão Telegram VINCULADA (REQ-006)."""

    async def _fake_resolve_user_id() -> str | None:
        return user_id

    monkeypatch.setattr(st, "resolve_user_id", _fake_resolve_user_id)


def _no_admins(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get_user_by_id(user_id: str) -> User | None:
        return User(
            id=user_id,
            username="u",
            password_hash="h",
            role="user",
            is_active=True,
            created_at=_PLACEHOLDER_CREATED_AT,
        )

    monkeypatch.setattr(st, "get_user_by_id", _fake_get_user_by_id)


def _admin_user(monkeypatch: pytest.MonkeyPatch, *, user_id: str) -> None:
    async def _fake_get_user_by_id(uid: str) -> User | None:
        if uid == user_id:
            return User(
                id=uid,
                username="a",
                password_hash="h",
                role="admin",
                is_active=True,
                created_at=_PLACEHOLDER_CREATED_AT,
            )
        return User(
            id=uid,
            username="u",
            password_hash="h",
            role="user",
            is_active=True,
            created_at=_PLACEHOLDER_CREATED_AT,
        )

    monkeypatch.setattr(st, "get_user_by_id", _fake_get_user_by_id)


def _make_task(*, id_: str, owner: str, thread_id: str = "th-1") -> ScheduledTask:
    return ScheduledTask(
        id=id_,
        prompt="x",
        thread_id=thread_id,
        schedule=Schedule(kind="once", expr="2026-12-31T23:59:00"),
        owner_user_key=owner,
    )


# ===========================================================================
# create_scheduled_task — REQ-003
# ===========================================================================


class _FakeDeliveryResolver:
    def __init__(
        self,
        *,
        result: str | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[str, str | None]] = []

    async def resolve(
        self, *, user_id: str, delivery_channel: str | None
    ) -> str | None:
        self.calls.append((user_id, delivery_channel))
        if self.error is not None:
            raise self.error
        if delivery_channel is None:
            return None
        return self.result


async def test_create_resolves_owner_user_key_from_configurable(monkeypatch):
    _configurable(monkeypatch, user_key="web:user-a", thread_id="th-9")
    repo = _FakeRepository()
    sched = _FakeScheduler()
    monkeypatch.setattr(
        st,
        "build_create_scheduled_task",
        lambda: CreateScheduledTask(
            repository=repo,
            scheduler=sched,
            delivery_resolver=_FakeDeliveryResolver(),
        ),
    )

    result = await st.create_scheduled_task.ainvoke(
        {"prompt": "lembra amanhã", "schedule_kind": "once", "schedule_expr": "2026-12-31T23:59:00"}
    )

    assert result["owner_user_key"] == "web:user-a"
    assert result["thread_id"] == "th-9"
    saved = await repo.get(result["id"])
    assert saved is not None
    assert saved.owner_user_key == "web:user-a"
    assert sched.scheduled == [result["id"]]


def test_create_scheduled_task_does_not_expose_owner_or_raw_delivery_user_key():
    """tools-1 unit-2 / REQ-003: sem spoof; delivery_channel opcional presente."""
    sig = inspect.signature(st.create_scheduled_task.coroutine)
    assert "owner_user_key" not in sig.parameters
    assert "delivery_user_key" not in sig.parameters
    assert "created_by" not in sig.parameters
    assert "delivery_channel" in sig.parameters
    assert sig.parameters["delivery_channel"].default is None


async def test_create_with_delivery_channel_returns_canonical_destination(monkeypatch):
    """tools-1 unit-1 / REQ-ADD-003: retorno com id, schedule e delivery_user_key."""
    from src.domain.shared.errors import DomainError

    _configurable(monkeypatch, user_key="web:user-a", thread_id="th-1")
    repo = _FakeRepository()
    sched = _FakeScheduler()
    resolver = _FakeDeliveryResolver(result="whatsapp:5511999999999")
    monkeypatch.setattr(
        st,
        "build_create_scheduled_task",
        lambda: CreateScheduledTask(
            repository=repo,
            scheduler=sched,
            delivery_resolver=resolver,
        ),
    )

    result = await st.create_scheduled_task.ainvoke(
        {
            "prompt": "mande no zap",
            "schedule_kind": "once",
            "schedule_expr": "2026-12-31T23:59:00",
            "delivery_channel": "whatsapp",
        }
    )

    assert "error" not in result
    assert result["id"]
    assert result["schedule"] == {"kind": "once", "expr": "2026-12-31T23:59:00"}
    assert result["delivery_user_key"] == "whatsapp:5511999999999"
    assert result["effective_delivery_user_key"] == "whatsapp:5511999999999"
    assert resolver.calls == [("user-a", "whatsapp")]
    assert sched.scheduled == [result["id"]]


async def test_create_delivery_channel_without_link_returns_error(monkeypatch):
    """Erro de vínculo → {"error": ...} sem criar tarefa."""
    from src.domain.shared.errors import DomainError

    _configurable(monkeypatch, user_key="web:user-a", thread_id="th-1")
    repo = _FakeRepository()
    sched = _FakeScheduler()
    resolver = _FakeDeliveryResolver(
        error=DomainError("canal whatsapp sem vínculo ativo")
    )
    monkeypatch.setattr(
        st,
        "build_create_scheduled_task",
        lambda: CreateScheduledTask(
            repository=repo,
            scheduler=sched,
            delivery_resolver=resolver,
        ),
    )

    result = await st.create_scheduled_task.ainvoke(
        {
            "prompt": "x",
            "schedule_kind": "once",
            "schedule_expr": "2026-12-31T23:59:00",
            "delivery_channel": "whatsapp",
        }
    )

    assert "error" in result
    assert "whatsapp" in result["error"].lower()
    assert sched.scheduled == []
    assert await repo.list_all() == []


async def test_create_without_identity_returns_error_not_exception(monkeypatch):
    _configurable(monkeypatch)  # sem user_key
    result = await st.create_scheduled_task.ainvoke(
        {"prompt": "x", "schedule_kind": "once", "schedule_expr": "2026-12-31T23:59:00"}
    )
    assert "error" in result


async def test_create_runs_without_approval_tier_2(monkeypatch):
    """Tier 2: chama execute() e retorna direto — sem interrupt()/HITL no meio do caminho."""
    _configurable(monkeypatch, user_key="web:user-a", thread_id="th-1")
    repo = _FakeRepository()
    sched = _FakeScheduler()
    monkeypatch.setattr(
        st,
        "build_create_scheduled_task",
        lambda: CreateScheduledTask(
            repository=repo,
            scheduler=sched,
            delivery_resolver=_FakeDeliveryResolver(),
        ),
    )
    result = await st.create_scheduled_task.ainvoke(
        {"prompt": "x", "schedule_kind": "cron", "schedule_expr": "0 9 * * *"}
    )
    assert result["status"] == "scheduled"


async def test_create_invalid_schedule_returns_error(monkeypatch):
    _configurable(monkeypatch, user_key="web:user-a")
    result = await st.create_scheduled_task.ainvoke(
        {"prompt": "x", "schedule_kind": "once", "schedule_expr": "not-a-date"}
    )
    assert "error" in result


async def test_create_invalid_tool_scope_returns_error(monkeypatch):
    _configurable(monkeypatch, user_key="web:user-a")
    result = await st.create_scheduled_task.ainvoke(
        {
            "prompt": "x",
            "schedule_kind": "once",
            "schedule_expr": "2026-12-31T23:59:00",
            "tool_scope": "super-admin",
        }
    )
    assert "error" in result


# ===========================================================================
# list_scheduled_tasks — REQ-004/REQ-008
# ===========================================================================


async def test_list_scopes_to_caller_when_not_admin(monkeypatch):
    _configurable(monkeypatch, user_key="web:user-a")
    _no_admins(monkeypatch)
    repo = _FakeRepository()
    await repo.save(_make_task(id_="t-a", owner="web:user-a"))
    await repo.save(_make_task(id_="t-b", owner="web:user-b"))
    monkeypatch.setattr(st, "build_list_scheduled_tasks", lambda: ListScheduledTasks(repository=repo))

    result = await st.list_scheduled_tasks.ainvoke({})

    assert [t["id"] for t in result] == ["t-a"]


async def test_list_returns_all_when_admin(monkeypatch):
    _configurable(monkeypatch, user_key="web:admin-1")
    _admin_user(monkeypatch, user_id="admin-1")
    repo = _FakeRepository()
    await repo.save(_make_task(id_="t-a", owner="web:user-a"))
    await repo.save(_make_task(id_="t-b", owner="web:user-b"))
    monkeypatch.setattr(st, "build_list_scheduled_tasks", lambda: ListScheduledTasks(repository=repo))

    result = await st.list_scheduled_tasks.ainvoke({})

    assert sorted(t["id"] for t in result) == ["t-a", "t-b"]


async def test_list_telegram_caller_is_never_admin(monkeypatch):
    """`telegram:<chat_id>` SEM vínculo em `user_integrations` é is_admin=False
    (`resolve_user_id()` retorna `None` — nada para consultar em `users`)."""
    _configurable(monkeypatch, user_key="telegram:555")
    repo = _FakeRepository()
    await repo.save(_make_task(id_="t-mine", owner="telegram:555"))
    await repo.save(_make_task(id_="t-other", owner="web:user-b"))
    monkeypatch.setattr(st, "build_list_scheduled_tasks", lambda: ListScheduledTasks(repository=repo))

    result = await st.list_scheduled_tasks.ainvoke({})

    assert [t["id"] for t in result] == ["t-mine"]


async def test_list_telegram_caller_resolves_admin_when_linked(monkeypatch):
    """REQ-006 (telegram-channel delta), unit `resolve-2-unit-3`: uma sessão
    Telegram COM vínculo ativo (`resolve_user_id()` retorna um `user_id`
    real) consulta `role` como uma sessão web resolveria — prova de que
    `_resolve_caller_identity` usa mesmo o resolvedor centralizado, não um
    caminho que sempre devolve `None` para Telegram."""
    _configurable(monkeypatch, user_key="telegram:555")
    _stub_resolved_user_id(monkeypatch, "admin-1")
    _admin_user(monkeypatch, user_id="admin-1")
    repo = _FakeRepository()
    await repo.save(_make_task(id_="t-a", owner="web:user-a"))
    await repo.save(_make_task(id_="t-b", owner="telegram:555"))
    monkeypatch.setattr(st, "build_list_scheduled_tasks", lambda: ListScheduledTasks(repository=repo))

    result = await st.list_scheduled_tasks.ainvoke({})

    assert sorted(t["id"] for t in result) == ["t-a", "t-b"]


async def test_list_without_identity_returns_error(monkeypatch):
    _configurable(monkeypatch)
    result = await st.list_scheduled_tasks.ainvoke({})
    assert "error" in result


# ===========================================================================
# cancel_scheduled_task — REQ-004/REQ-008
# ===========================================================================


async def test_cancel_own_task_succeeds(monkeypatch):
    _configurable(monkeypatch, user_key="web:user-a")
    _no_admins(monkeypatch)
    repo = _FakeRepository()
    sched = _FakeScheduler()
    await repo.save(_make_task(id_="t-1", owner="web:user-a"))
    monkeypatch.setattr(
        st,
        "build_cancel_scheduled_task",
        lambda: CancelScheduledTask(repository=repo, scheduler=sched),
    )

    result = await st.cancel_scheduled_task.ainvoke({"task_id": "t-1"})

    assert result == {"success": True, "task_id": "t-1"}
    assert await repo.get("t-1") is None
    assert sched.unscheduled == ["t-1"]


async def test_cancel_others_task_without_admin_returns_clean_error(monkeypatch):
    """A tool NÃO deixa vazar stack trace — traduz para `{"error": ...}` (REQ-008)."""
    _configurable(monkeypatch, user_key="web:user-b")
    _no_admins(monkeypatch)
    repo = _FakeRepository()
    sched = _FakeScheduler()
    await repo.save(_make_task(id_="t-victim", owner="web:user-a"))
    monkeypatch.setattr(
        st,
        "build_cancel_scheduled_task",
        lambda: CancelScheduledTask(repository=repo, scheduler=sched),
    )

    result = await st.cancel_scheduled_task.ainvoke({"task_id": "t-victim"})

    assert "error" in result
    assert "t-victim" in result["error"]
    # Não removeu nada — autorização negada antes de qualquer efeito colateral.
    assert await repo.get("t-victim") is not None
    assert sched.unscheduled == []


async def test_admin_cancels_others_task(monkeypatch):
    _configurable(monkeypatch, user_key="web:admin-1")
    _admin_user(monkeypatch, user_id="admin-1")
    repo = _FakeRepository()
    sched = _FakeScheduler()
    await repo.save(_make_task(id_="t-x", owner="web:user-b"))
    monkeypatch.setattr(
        st,
        "build_cancel_scheduled_task",
        lambda: CancelScheduledTask(repository=repo, scheduler=sched),
    )

    result = await st.cancel_scheduled_task.ainvoke({"task_id": "t-x"})

    assert result == {"success": True, "task_id": "t-x"}
    assert await repo.get("t-x") is None


async def test_cancel_without_identity_returns_error(monkeypatch):
    _configurable(monkeypatch)
    result = await st.cancel_scheduled_task.ainvoke({"task_id": "t-1"})
    assert "error" in result


# ===========================================================================
# Registro Tier 2 + grafo unificado
# ===========================================================================


@pytest.mark.parametrize(
    "tool_name",
    ["create_scheduled_task", "list_scheduled_tasks", "cancel_scheduled_task"],
)
def test_tools_registered_as_tier_2(tool_name: str):
    from src.agents.unified.tier_config import TIER_REGISTRY

    assert TIER_REGISTRY.get(tool_name) == 2


@pytest.mark.parametrize(
    "tool_name",
    ["create_scheduled_task", "list_scheduled_tasks", "cancel_scheduled_task"],
)
def test_tools_registered_in_unified_graph(tool_name: str):
    from src.agents.unified.agent import _TOOL_NAMES

    assert tool_name in _TOOL_NAMES


# ===========================================================================
# Builders do composition root (change `wire-scheduling-tools-to-agent`)
# ===========================================================================
# REQ-013 cenário 2: cada builder devolve o use case ligado ao mesmo
# `PostgresScheduledTaskRepository` que `scheduling_router.py` já usa inline
# e ao `task_scheduler` singleton — exceto `ListScheduledTasks`, que não
# agenda nem desagenda (só lê).


def test_build_create_scheduled_task_uses_postgres_repo_and_singleton_scheduler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-2 / REQ-013: `build_create_scheduled_task` MUST devolver
    `CreateScheduledTask` com `PostgresScheduledTaskRepository(os.environ["POSTGRES_URI"])`
    e o `task_scheduler` singleton."""
    from src.application.use_cases.create_scheduled_task import CreateScheduledTask
    from src.composition.dependencies import build_create_scheduled_task
    from src.infrastructure.persistence.scheduled_task_repository import (
        PostgresScheduledTaskRepository,
    )
    from src.infrastructure.scheduling.scheduler_instance import task_scheduler

    monkeypatch.setenv("POSTGRES_URI", "postgresql://builder-test@localhost/db")

    use_case = build_create_scheduled_task()

    assert isinstance(use_case, CreateScheduledTask)
    assert isinstance(use_case._repository, PostgresScheduledTaskRepository)
    assert use_case._repository._conninfo == "postgresql://builder-test@localhost/db"
    assert use_case._scheduler is task_scheduler
    assert use_case._delivery_resolver is not None


def test_build_list_scheduled_tasks_uses_postgres_repo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-3 / REQ-013: `build_list_scheduled_tasks` MUST devolver
    `ListScheduledTasks` com o mesmo `PostgresScheduledTaskRepository` (sem
    scheduler — listagem não agenda/desagenda nada)."""
    from src.application.use_cases.list_scheduled_tasks import ListScheduledTasks
    from src.composition.dependencies import build_list_scheduled_tasks
    from src.infrastructure.persistence.scheduled_task_repository import (
        PostgresScheduledTaskRepository,
    )

    monkeypatch.setenv("POSTGRES_URI", "postgresql://builder-test@localhost/db")

    use_case = build_list_scheduled_tasks()

    assert isinstance(use_case, ListScheduledTasks)
    assert isinstance(use_case._repository, PostgresScheduledTaskRepository)
    assert use_case._repository._conninfo == "postgresql://builder-test@localhost/db"
    # Listagem é puro read — não tem scheduler.
    assert not hasattr(use_case, "_scheduler")


def test_build_cancel_scheduled_task_uses_postgres_repo_and_singleton_scheduler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-4 / REQ-013: `build_cancel_scheduled_task` MUST devolver
    `CancelScheduledTask` com o mesmo `PostgresScheduledTaskRepository` e o
    `task_scheduler` singleton (cancelamento precisa desagendar o trigger)."""
    from src.application.use_cases.cancel_scheduled_task import CancelScheduledTask
    from src.composition.dependencies import build_cancel_scheduled_task
    from src.infrastructure.persistence.scheduled_task_repository import (
        PostgresScheduledTaskRepository,
    )
    from src.infrastructure.scheduling.scheduler_instance import task_scheduler

    monkeypatch.setenv("POSTGRES_URI", "postgresql://builder-test@localhost/db")

    use_case = build_cancel_scheduled_task()

    assert isinstance(use_case, CancelScheduledTask)
    assert isinstance(use_case._repository, PostgresScheduledTaskRepository)
    assert use_case._repository._conninfo == "postgresql://builder-test@localhost/db"
    assert use_case._scheduler is task_scheduler


def test_scheduling_tools_not_in_interrupt_on() -> None:
    """Unit-2 / REQ-015: as três tools de agendamento NÃO entram em
    `_interrupt_on` — `create_scheduled_task` (e as outras) executam direto
    numa conversa normal (Tier 2), sem pausar aguardando aprovação.

    `build_interrupt_on` é deny-by-default: se a tool NÃO está no
    `TIER_REGISTRY`, ela entra no gate. Por isso o teste asserta
    explicitamente que as três estão fora do dict — pra travar a regressão
    no caso de alguém removê-las de `TIER_2_TOOLS` por engano.
    """
    from src.agents.unified.agent import _TOOL_NAMES
    from src.agents.unified.tier_config import build_interrupt_on

    interrupt_on = build_interrupt_on(_TOOL_NAMES)
    for name in (
        "create_scheduled_task",
        "list_scheduled_tasks",
        "cancel_scheduled_task",
    ):
        assert name not in interrupt_on, (
            f"{name} está em _interrupt_on — deveria rodar direto (Tier 2)."
        )


def test_create_and_list_scheduled_tasks_pass_envelope_without_grant() -> None:
    """Trava de regressão: `create_scheduled_task` e `list_scheduled_tasks`
    DEVEM estar classificadas no `TOOL_EFFECTS` com capability no piso
    (`WRITE_NEW` / `READ`), para que o `EnvelopeMiddleware` não as bloqueie
    em chamadas Tier 2 sem envelope.

    Achado em produção (2026-08-06, run 019fd7f0-ab02): as 3 tools estavam
    registradas em `_UNIFIED_TOOLS` e `TIER_REGISTRY=2`, mas faltavam em
    `TOOL_EFFECTS` — caíam em `UNKNOWN` (fora do piso) e o `wrap_tool_call`
    bloqueava cada invocação com `envelope_audit event=block required='unknown'`.
    O modelo desistia e alucinava que "não tem scheduler interno".

    `cancel_scheduled_task` está EXPLICITAMENTE fora: remover um trigger
    existente é `WRITE_EXISTING` (fora do piso, exige concessão), e a
    decisão de design entre Tier 2 e Tier 3 está aberta (ver
    `wire-scheduling-tools-to-agent-task-verify-1` reaberto).
    """
    from src.agents.unified.effects import TOOL_EFFECTS, classify, needs_grant

    # `create_scheduled_task` cria recurso novo → `WRITE_NEW` (piso).
    assert "create_scheduled_task" in TOOL_EFFECTS
    assert classify("create_scheduled_task") == (Capability.WRITE_NEW,)
    assert not needs_grant("create_scheduled_task"), (
        "create_scheduled_task deveria rodar sem grant (WRITE_NEW no piso)."
    )

    # `list_scheduled_tasks` é puro read.
    assert "list_scheduled_tasks" in TOOL_EFFECTS
    assert classify("list_scheduled_tasks") == (Capability.READ,)
    assert not needs_grant("list_scheduled_tasks"), (
        "list_scheduled_tasks deveria rodar sem grant (READ no piso)."
    )

    # `cancel_scheduled_task` está intencionalmente fora — não fix mínimo.
    # Trava: qualquer um que tentar classificá-lo como `WRITE_NEW` (meia-verdade)
    # ou como `WRITE_EXISTING` (vai precisar de grant, quebrando o Tier 2
    # prometido pelo design) precisa abrir uma change formal primeiro.
    assert "cancel_scheduled_task" not in TOOL_EFFECTS, (
        "cancel_scheduled_task NÃO deve ser classificado sem uma change "
        "explícita (tensão Tier 2 vs Tier 3 — ver reabertura da change "
        "wire-scheduling-tools-to-agent)."
    )
