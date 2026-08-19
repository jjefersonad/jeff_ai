"""Domínio `agents` — entidade `AgentProfile` e erros relacionados.

PURO: zero import de framework. Persistência e HTTP ficam em
`infrastructure/`; casos de uso (CRUD, listagem, ativação) ficam em
`application/`.
"""
from src.domain.agents.errors import (
    DuplicateAgentProfileError,
    InvalidAgentProfileError,
    InvalidModelOverrideError,
)
from src.domain.agents.models import AgentProfile

__all__ = [
    "AgentProfile",
    "DuplicateAgentProfileError",
    "InvalidAgentProfileError",
    "InvalidModelOverrideError",
]
