"""Caso de uso: listar AgentProfiles do usuário (REQ-002 do spec `agent-profile-crud`)."""
from __future__ import annotations

from src.application.ports.agent_profile_repository import (
    AgentProfileRepositoryPort,
)
from src.domain.agents import AgentProfile


class ListAgentProfiles:
    """Lista AgentProfiles do `user_id`."""

    def __init__(self, *, repository: AgentProfileRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self, *, user_id: str, include_archived: bool = False
    ) -> list[AgentProfile]:
        """Retorna os perfis do `user_id`; arquivados ocultos por padrão."""
        return await self._repository.list_by_user(
            user_id, include_archived=include_archived
        )
