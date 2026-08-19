"""Caso de uso: arquivar AgentProfile (REQ-005 do spec `agent-profile-crud`)."""
from __future__ import annotations

from src.application.ports.agent_profile_repository import (
    AgentProfileRepositoryPort,
)
from src.domain.agents import AgentProfile


class ArchiveAgentProfile:
    """Soft-delete: marca o perfil como arquivado."""

    def __init__(self, *, repository: AgentProfileRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self, *, user_id: str, profile_id: str
    ) -> AgentProfile | None:
        """Arquiva o perfil próprio; ``None`` se miss / cross-user."""
        return await self._repository.archive(user_id, profile_id)
