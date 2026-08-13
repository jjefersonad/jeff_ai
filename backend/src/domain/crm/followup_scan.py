"""Stub isolado do scan periódico de follow-up (D-006 sales-pipeline-via-agent).

Estado atual: o scan **NÃO está em produção**. A task `sales_followup_scan`
é parte da change `agendamento-jeff-cli` (ainda em draft) que vai plugar o
retorno de `periodic_scheduled_tasks()` no boot do `webapp.py`. Este
módulo expõe o que vai ser usado por essa change, isolado por uma flag
de ambiente (default off).

Superfície atual:

- `sales_followup_scan(deals, last_note_at)` — função **pura** que devolve
  os deals estagnados (reusa `next_best_action.suggest_all`). Já está
  pronta para ser chamada por testes ou pelo `_fire_job` do scheduler
  quando a integração existir.

- `periodic_scheduled_tasks()` — **única fronteira com o mundo**; lê
  `JEFF_AI_SALES_FOLLOWUP_SCAN_INTERVAL_HOURS` do ambiente (default 0 =
  desabilitado) e devolve a `ScheduledTask` periódica correspondente.
  Quando `agendamento-jeff-cli` for mergeada, este retorno alimenta o
  registro de triggers no boot (junto com `_reschedule_pending_tasks` em
  `webapp.py`); até lá, a lista é vazia por default e o sistema se
  comporta como antes desta task.

Por design, este módulo é **fail-safe**: zero scan roda hoje, mesmo
com `JEFF_AI_SALES_FOLLOWUP_SCAN_INTERVAL_HOURS>0`, porque o boot ainda
não consome `periodic_scheduled_tasks()`. O scan só vira realidade
quando a change `agendamento-jeff-cli` plugar este retorno no
`webapp.py` — ver `sales_followup_scan` acima para a fiação esperada.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime

from src.domain.crm.models import Deal
from src.domain.crm.next_best_action import suggest_all
from src.domain.scheduling import Schedule, ScheduledTask

# Identificador canônico da task no scheduler. Constante para evitar
# divergência entre o `id` da `ScheduledTask` e o nome que o operador
# (ou o boot) possa referenciar.
SCAN_TASK_ID = "sales_followup_scan"

# Default 0 = desabilitado. Só habilita quando o operador quiser +
# quando `agendamento-jeff-cli` plugar este retorno no boot.
_DEFAULT_SCAN_INTERVAL_HOURS = 0

# Intervalo default documentado em D-006 — usado quando o operador
# setar a env para um valor positivo mas não múltiplo de hora inteira
# (ex.: 6h). Mantido aqui como referência.
_DOC_DEFAULT_INTERVAL_HOURS = 6


def sales_followup_scan(
    deals: list[Deal],
    last_note_at: Mapping[str, datetime | None] | None = None,
    *,
    now: datetime | None = None,
) -> list[Deal]:
    """Devolve os deals estagnados (cap de 10, mais antigos primeiro).

    Wrappa `next_best_action.suggest_all` com a mesma assinatura, para
    que o scheduler (quando o trigger `sales_followup_scan` disparar)
    possa chamar esta função diretamente. O resultado é a lista de
    `Deal` que o agente deve usar para montar o resumo na thread do
    usuário — nada além do que REQ-004 já exige.

    Mantida **pura** (zero framework) pelo mesmo princípio de
    `next_best_action.suggest`/`stagnation.is_stale` — a única
    diferença é a borda: este módulo é o "nome" público da task no
    scheduler, enquanto a lógica vive onde já é testada.
    """
    return suggest_all(deals, last_note_at=last_note_at, now=now)


def _resolve_scan_interval_hours() -> int:
    """Lê `JEFF_AI_SALES_FOLLOWUP_SCAN_INTERVAL_HOURS` do ambiente.

    Retorna 0 (desabilitado) em qualquer caso inválido — fail-safe, igual
    ao default. Operador que setar valor não-numérico ou negativo cai em
    "desabilitado" em vez de quebrar o boot.
    """
    raw = os.environ.get("JEFF_AI_SALES_FOLLOWUP_SCAN_INTERVAL_HOURS")
    if raw is None or raw.strip() == "":
        return _DEFAULT_SCAN_INTERVAL_HOURS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_SCAN_INTERVAL_HOURS
    return value if value > 0 else 0


def periodic_scheduled_tasks() -> list[ScheduledTask]:
    """Devolve a lista de `ScheduledTask` periódicas auto-registradas.

    Por enquanto contém apenas `sales_followup_scan`. Quando o operador
    setar `JEFF_AI_SALES_FOLLOWUP_SCAN_INTERVAL_HOURS>0` (default de
    referência: 6h), a task aparece aqui. Caso contrário, lista vazia —
    o sistema se comporta como antes desta task.

    Integração esperada (a ser feita pela change `agendamento-jeff-cli`,
    ainda em draft): `webapp.py` chama isto no boot e mescla com
    `_reschedule_pending_tasks` para registrar o trigger no
    `APSchedulerTaskScheduler`. Esta task **NÃO** toca o `webapp.py`
    para manter o desacoplamento até a outra change ficar pronta.
    """
    interval_hours = _resolve_scan_interval_hours()
    if interval_hours <= 0:
        return []
    # Cron "0 */N * * *" = minuto 0 de cada N-ésima hora, todo dia.
    cron_expr = f"0 */{interval_hours} * * *"
    task = ScheduledTask(
        id=SCAN_TASK_ID,
        # Prompt de orientação: o agente recebe a lista de deals
        # estagnados via `crm_notes` (caminho já implementado em
        # `next_best_action.suggest_all`) e posta o resumo na thread
        # do usuário. A `next_best_action` é a fonte de verdade; o
        # prompt é só a fiação.
        prompt=(
            "Rode `next_best_action.suggest_all()` para listar os deals "
            "estagnados do CRM e poste um resumo na thread do usuário: "
            "'N deals estagnados. Abrir o funil para ver?'. O agente NÃO "
            "deve auto-executar follow-up — apenas listar e pedir ação."
        ),
        thread_id="default_thread",
        schedule=Schedule(kind="cron", expr=cron_expr),
    )
    return [task]
