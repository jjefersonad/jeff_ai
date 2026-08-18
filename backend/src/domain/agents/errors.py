"""Erros de domínio do vertical `agents` (sem dependência de framework)."""
from __future__ import annotations

from src.domain.shared.errors import DomainError


class DuplicateAgentProfileError(DomainError):
    """Já existe um `AgentProfile` com o mesmo `(user_id, slug)` para esse usuário."""
