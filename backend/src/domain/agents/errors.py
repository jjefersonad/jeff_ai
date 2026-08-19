"""Erros de domínio do vertical `agents` (sem dependência de framework)."""
from __future__ import annotations

from src.domain.shared.errors import DomainError


class DuplicateAgentProfileError(DomainError):
    """Já existe um `AgentProfile` com o mesmo `(user_id, slug)` para esse usuário."""


class InvalidAgentProfileError(DomainError):
    """`profile_id` inválido: miss, cross-user, arquivado, ou `user_id` irresolvível."""


class InvalidModelOverrideError(DomainError):
    """`model_override` não resolve para um backend conhecido do grafo `unified`."""
