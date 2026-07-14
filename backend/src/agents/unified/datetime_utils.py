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


def _resolve_tz() -> ZoneInfo:
    """Resolve o timezone do env `JEFF_AI_TZ` (IANA name), com fallback seguro.

    - Env setado e válido: retorna `ZoneInfo(JEFF_AI_TZ)`.
    - Env setado mas inválido (e.g., `JEFF_AI_TZ=Atlantis/Lemuria`): loga
      warning e retorna `ZoneInfo("UTC")` — não raise, não quebra o boot.
    - Env não setado: retorna `ZoneInfo("UTC")` (default documentado).
    """
    name = os.environ.get("JEFF_AI_TZ", "UTC")
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        _log.warning("JEFF_AI_TZ=%s inválido; usando UTC", name)
        return ZoneInfo("UTC")


__all__ = ["_resolve_tz"]
