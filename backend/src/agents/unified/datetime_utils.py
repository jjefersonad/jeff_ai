"""Helpers de data/hora compartilhados entre `agent.py` e tools.

Vive aqui (e não em `agent.py`) porque ambos os módulos precisam importar
`_resolve_tz` — colocá-lo em `agent.py` cria ciclo (agent → tavily_tool →
agent, parcial). Mover para cá resolve o ciclo sem precisar de um utils
genérico (que seria over-engineering para 1 função).

O design original (D6) previu que `agent.py` seria o dono; o ciclo não
foi detectado porque o design foi escrito em abstract, sem rodar o import.
A spec REQ-003 de `current-date-context` exige que `_resolve_tz` seja
**exportada de `agent.py`** — esse requisito é interpretado como
"disponível para reuso"; o caminho de import pode mudar (agent re-exporta
para compat).
"""
from __future__ import annotations

import logging
import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_log = logging.getLogger(__name__)


def _tz_name() -> str:
    """Nome IANA operacional: `JEFF_AI_TZ`, senão `TZ` do processo, senão UTC."""
    return os.environ.get("JEFF_AI_TZ") or os.environ.get("TZ") or "UTC"


def _resolve_tz() -> ZoneInfo:
    """Resolve o timezone operacional, com fallback seguro.

    Ordem: `JEFF_AI_TZ` → `TZ` (fuso do container/SO) → `UTC`.

    - Nome válido: retorna `ZoneInfo(name)`.
    - Nome inválido (e.g. `Atlantis/Lemuria`): loga warning e retorna
      `ZoneInfo("UTC")` — não raise, não quebra o boot.
    """
    name = _tz_name()
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        _log.warning("timezone=%s inválido (JEFF_AI_TZ/TZ); usando UTC", name)
        return ZoneInfo("UTC")


__all__ = ["_resolve_tz", "_tz_name"]
