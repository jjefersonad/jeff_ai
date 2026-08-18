"""Caso de uso: obter um AgentProfile (REQ-003 do spec `agent-profile-crud`)."""
from __future__ import annotations

from src.application.ports.agent_profile_repository import (
    AgentProfileRepositoryPort,
)
from src.domain.agents import AgentProfile


class GetAgentProfile:
    """Retorna um AgentProfile do `user_id`."""

    def __init__(self, *, repository: AgentProfileRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self, *, user_id: str, profile_id: str
    ) -> AgentProfile | None:
        """Retorna o perfil próprio ou ``None`` (miss / cross-user)."""
        return await self._repository.get(user_id, profile_id)
