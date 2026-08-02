"""Domínio de scheduling — entidades, value objects e máquina de estado.

PURO: zero import de framework. Toda regra de negócio sobre `ScheduledTask`
vive aqui; persistência, scheduler, e execução do agente ficam em
`infrastructure/`.
"""
from src.domain.scheduling.scheduled_task import (
    Schedule,
    ScheduledTask,
    TaskStatus,
    ToolScope,
)

__all__ = ["Schedule", "ScheduledTask", "TaskStatus", "ToolScope"]
