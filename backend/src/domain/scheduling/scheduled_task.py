"""Domínio de scheduling: entidade `ScheduledTask`, value object `Schedule`, enums.

PURO: zero import de framework. Toda regra de negócio sobre o ciclo de vida
de uma tarefa agendada (transições, validação de schedule, timeout) vive
aqui — persistência, scheduler e execução do agente ficam em
`infrastructure/`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from src.domain.shared.errors import DomainError

# ============================================================================
# Enums
# ============================================================================


class TaskStatus(str, Enum):
    """Máquina de estado da tarefa.

    Transições válidas (ver REQ-002 do spec `task-scheduling` +
    `scheduled-human-intervention`):
      SCHEDULED → RUNNING → SUCCEEDED
                          ↘ FAILED
                          ↘ WAITING_HUMAN  (HITL; resume completa depois)
      SUCCEEDED|FAILED → SCHEDULED  (somente via rearm_for_cron)
    """

    SCHEDULED = "scheduled"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    WAITING_HUMAN = "waiting_human"


class ToolScope(str, Enum):
    """Escopo de ferramentas que a execução de uma tarefa tem disponível.

    `RESTRICTED` (default): só tools Tier 1/2 ficam disponíveis — escrita de
    arquivos novos e geração de imagens sem gate humano. Escolha segura.
    `FULL`: a tarefa roda com o conjunto completo de tools (incluindo Tier 3/4),
    e qualquer tool que toque gate humano (`interrupt_on`) pausa a execução
    aguardando aprovação — mesmo comportamento de uma conversa pausada.
    """

    RESTRICTED = "restricted"
    FULL = "full"


# ============================================================================
# Value object: Schedule
# ============================================================================


ScheduleKind = Literal["once", "cron"]
NotifyStatus = Literal["delivered", "skipped", "failed"]

# Motivos canônicos de skip de notify (REQ-002 scheduled-job-observability).
NOTIFY_SKIP_OUTPUT_MISSING = "output_missing"
NOTIFY_SKIP_DELIVERY_USER_KEY_MISSING = "delivery_user_key_missing"


_CRON_FIELDS = 5  # APScheduler/cron padrão: minuto hora dia mês dia-da-semana
_CRON_FIELD_RANGE = (0, 23)  # usado para validar limites de forma conservadora


@dataclass(frozen=True)
class Schedule:
    """Define QUANDO a tarefa deve rodar.

    `kind="once"`  → `expr` é uma data ISO 8601 (`YYYY-MM-DDTHH:MM:SS`).
    `kind="cron"`  → `expr` é uma expressão cron de 5 campos
                     (`"min hour day month weekday"`).
    """

    kind: ScheduleKind
    expr: str

    def __post_init__(self) -> None:
        """Valida o `kind` e a `expr` correspondente."""
        if self.kind not in ("once", "cron"):
            raise DomainError(
                f"Schedule.kind deve ser 'once' ou 'cron'; recebido: {self.kind!r}"
            )
        if not isinstance(self.expr, str) or not self.expr.strip():
            raise DomainError("Schedule.expr é obrigatório e não pode ser vazio.")
        # Normaliza whitespace
        object.__setattr__(self, "expr", self.expr.strip())

        if self.kind == "once":
            self._validate_iso8601(self.expr)
        else:  # "cron"
            self._validate_cron(self.expr)

    @staticmethod
    def _validate_iso8601(expr: str) -> None:
        try:
            # Aceita tanto "2026-12-31T23:59:00" quanto "...+00:00"
            datetime.fromisoformat(expr)
        except ValueError as exc:
            raise DomainError(
                f"Schedule(kind='once').expr deve ser uma data ISO 8601 válida "
                f"(ex.: '2026-12-31T23:59:00'); recebido: {expr!r}"
            ) from exc

    @staticmethod
    def _validate_cron(expr: str) -> None:
        fields = expr.split()
        if len(fields) != _CRON_FIELDS:
            raise DomainError(
                f"Schedule(kind='cron').expr deve ter {_CRON_FIELDS} campos "
                f"('min hour day month weekday'); recebido: {expr!r} "
                f"({len(fields)} campos)"
            )
        for field_value in fields:
            if not _is_cron_field_numeric(field_value):
                raise DomainError(
                    f"Schedule(kind='cron').expr contém campo não numérico: "
                    f"{field_value!r} em {expr!r}"
                )
        # Validação leve de range: pelo menos os 2 primeiros campos (minuto/hora)
        # devem estar em [0, 59] / [0, 23]. Para valores como `*` ou `*/15`
        # aceitamos o ponto de partida numérico.
        minute = _leading_int(fields[0])
        hour = _leading_int(fields[1])
        if minute is not None and not 0 <= minute <= 59:
            raise DomainError(
                f"Schedule(kind='cron').expr minuto fora do range [0,59]: {expr!r}"
            )
        if hour is not None and not _CRON_FIELD_RANGE[0] <= hour <= _CRON_FIELD_RANGE[1]:
            raise DomainError(
                f"Schedule(kind='cron').expr hora fora do range [0,23]: {expr!r}"
            )


def _is_cron_field_numeric(field: str) -> bool:
    """Aceita `5`, `*/15`, `1-30`, `1,15,30`; rejeita `x`, `banana`."""
    for part in field.split(","):
        part = part.strip()
        if not part:
            return False
        # Aceita `*`, `*/n`, `a`, `a-b`, `a-b/n` — todos contendo só dígitos, *, /, -
        if not all(c.isdigit() or c in ("*", "/", "-") for c in part):
            return False
    return True


def _leading_int(field: str) -> int | None:
    """Extrai o primeiro número inteiro de um campo cron (ou None se `*`)."""
    if field.startswith("*"):
        return None
    digits = ""
    for c in field:
        if c.isdigit():
            digits += c
        else:
            break
    return int(digits) if digits else None


# ============================================================================
# Entidade: ScheduledTask
# ============================================================================


# 5 minutos — default sensato para tarefas curtas (one-shots de chat).
DEFAULT_TIMEOUT_SECONDS = 300

# Limite superior arbitrário para evitar timeout acidental de "infinito".
MAX_TIMEOUT_SECONDS = 24 * 60 * 60  # 1 dia


@dataclass
class ScheduledTask:
    """Tarefa agendada: prompt + schedule + escopo de tools + estado de execução.

    `id` é a chave primária no `scheduled_tasks` e também a string registrada
    no scheduler (cada trigger carrega só `task_id` — ver REQ-005).
    """

    id: str
    prompt: str
    thread_id: str
    schedule: Schedule
    tool_scope: ToolScope = ToolScope.RESTRICTED
    skills: tuple[str, ...] = ()
    owner_user_key: str | None = None
    delivery_user_key: str | None = None
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    status: TaskStatus = TaskStatus.SCHEDULED
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    notify_status: NotifyStatus | None = None
    notify_error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def effective_delivery_user_key(self) -> str | None:
        """Destino de notify/HITL: `delivery_user_key` ou fallback `owner_user_key`."""
        return self.delivery_user_key if self.delivery_user_key is not None else self.owner_user_key

    # ------------------------------------------------------------------
    # Validação de construção
    # ------------------------------------------------------------------

    def __post_init__(self) -> None:
        """Valida invariantes básicas e normaliza whitespace."""
        if not isinstance(self.id, str) or not self.id.strip():
            raise DomainError("ScheduledTask.id é obrigatório e não pode ser vazio.")
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            raise DomainError("ScheduledTask.prompt é obrigatório e não pode ser vazio.")
        if not isinstance(self.thread_id, str) or not self.thread_id.strip():
            raise DomainError("ScheduledTask.thread_id é obrigatório e não pode ser vazio.")
        if not isinstance(self.timeout_seconds, int) or self.timeout_seconds <= 0:
            raise DomainError(
                f"ScheduledTask.timeout_seconds deve ser inteiro positivo; "
                f"recebido: {self.timeout_seconds!r}"
            )
        if self.timeout_seconds > MAX_TIMEOUT_SECONDS:
            raise DomainError(
                f"ScheduledTask.timeout_seconds não pode exceder {MAX_TIMEOUT_SECONDS} "
                f"(24h); recebido: {self.timeout_seconds!r}"
            )
        # Normaliza whitespace em campos string sem perder imutabilidade do resto
        object.__setattr__(self, "id", self.id.strip())
        object.__setattr__(self, "prompt", self.prompt.strip())
        object.__setattr__(self, "thread_id", self.thread_id.strip())
        # Garante que skills é tupla (e não lista)
        object.__setattr__(self, "skills", tuple(self.skills))

    # ------------------------------------------------------------------
    # Máquina de estado (REQ-002)
    # ------------------------------------------------------------------

    def start(self) -> None:
        """SCHEDULED → RUNNING. Idempotente: chamar duas vezes é erro."""
        if self.status is not TaskStatus.SCHEDULED:
            raise DomainError(
                f"ScheduledTask.start() exige status=SCHEDULED; status atual: "
                f"{self.status.value!r}"
            )
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now(UTC)
        self.error = None

    def succeed(self) -> None:
        """Transiciona RUNNING → SUCCEEDED e carimba `finished_at`."""
        if self.status is not TaskStatus.RUNNING:
            raise DomainError(
                f"ScheduledTask.succeed() exige status=RUNNING; status atual: "
                f"{self.status.value!r}"
            )
        self.status = TaskStatus.SUCCEEDED
        self.finished_at = datetime.now(UTC)

    def fail(self, error: str) -> None:
        """Transiciona RUNNING → FAILED e grava a mensagem de erro em `error`."""
        if self.status is not TaskStatus.RUNNING:
            raise DomainError(
                f"ScheduledTask.fail() exige status=RUNNING; status atual: "
                f"{self.status.value!r}"
            )
        self.status = TaskStatus.FAILED
        self.finished_at = datetime.now(UTC)
        self.error = str(error)

    def waiting_human(self) -> None:
        """Transiciona RUNNING → WAITING_HUMAN (HITL; não é falha)."""
        if self.status is not TaskStatus.RUNNING:
            raise DomainError(
                f"ScheduledTask.waiting_human() exige status=RUNNING; status atual: "
                f"{self.status.value!r}"
            )
        self.status = TaskStatus.WAITING_HUMAN
        self.error = None

    def resume_succeed(self) -> None:
        """WAITING_HUMAN → SUCCEEDED após resume HITL aprovado."""
        if self.status is not TaskStatus.WAITING_HUMAN:
            raise DomainError(
                "ScheduledTask.resume_succeed() exige status=WAITING_HUMAN; "
                f"status atual: {self.status.value!r}"
            )
        self.status = TaskStatus.SUCCEEDED
        self.finished_at = datetime.now(UTC)
        self.error = None

    def resume_fail(self, error: str) -> None:
        """WAITING_HUMAN → FAILED após reject / falha no resume HITL."""
        if self.status is not TaskStatus.WAITING_HUMAN:
            raise DomainError(
                "ScheduledTask.resume_fail() exige status=WAITING_HUMAN; "
                f"status atual: {self.status.value!r}"
            )
        self.status = TaskStatus.FAILED
        self.finished_at = datetime.now(UTC)
        self.error = str(error)

    def rearm_for_cron(self) -> None:
        """SUCCEEDED|FAILED → SCHEDULED para o próximo tick cron.

        Só válido quando `schedule.kind == "cron"`. Tarefas `once` e
        estados não-terminais levantam `DomainError`.
        """
        if self.schedule.kind != "cron":
            raise DomainError(
                "ScheduledTask.rearm_for_cron() exige schedule.kind='cron'; "
                f"recebido: {self.schedule.kind!r}"
            )
        if self.status not in (TaskStatus.SUCCEEDED, TaskStatus.FAILED):
            raise DomainError(
                "ScheduledTask.rearm_for_cron() exige status=SUCCEEDED|FAILED; "
                f"status atual: {self.status.value!r}"
            )
        self.status = TaskStatus.SCHEDULED
        self.finished_at = None
        self.error = None

    # ------------------------------------------------------------------
    # Desfecho de notify (não altera máquina de estado de execução)
    # ------------------------------------------------------------------

    def mark_notify_delivered(self) -> None:
        """Registra notify entregue; não altera `status`/`error` de execução."""
        self.notify_status = "delivered"
        self.notify_error = None

    def mark_notify_skipped(self, reason: str) -> None:
        """Registra notify skipped com motivo canônico (ex. `output_missing`)."""
        self.notify_status = "skipped"
        self.notify_error = str(reason)

    def mark_notify_failed(self, error: str) -> None:
        """Registra falha de notify; não altera `status`/`error` de execução."""
        self.notify_status = "failed"
        self.notify_error = str(error)

    @property
    def is_terminal(self) -> bool:
        """True se a tarefa já terminou (não pode mais transicionar)."""
        return self.status in (TaskStatus.SUCCEEDED, TaskStatus.FAILED)
