"""Caso de uso: atualizar AgentProfile (REQ-004 do spec `agent-profile-crud`)."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.application.ports.agent_profile_repository import (
    AgentProfileRepositoryPort,
)
from src.domain.agents import AgentProfile
from src.domain.shared.errors import DomainError

UNSET: Any = object()


class UpdateAgentProfile:
    """Atualiza campos mutáveis de um AgentProfile próprio."""

    def __init__(self, *, repository: AgentProfileRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        profile_id: str,
        name: str | None = None,
        system_prompt: str | None = None,
        skills_allowlist: list[str] | None | object = UNSET,
        tools_allowlist: list[str] | None | object = UNSET,
        mcp_allowlist: list[str] | None | object = UNSET,
        tier: int | None = None,
        model_override: str | None | object = UNSET,
    ) -> AgentProfile | None:
        """Atualiza o perfil; ``None`` se miss / cross-user.

        Campos não enviados mantêm o valor atual; para limpar
        ``skills_allowlist``, ``tools_allowlist``, ``mcp_allowlist`` ou
        ``model_override`` enviar explicitamente ``None``.
        ``name``/``system_prompt``/``tier`` são obrigatórios e validados.

        Raises:
            DomainError: se ``name``/``system_prompt`` ficar vazio ou
                ``tier`` estiver fora de ``1..4``.
        """
        existing = await self._repository.get(user_id, profile_id)
        if existing is None:
            return None

        new_name = (
            name.strip() if isinstance(name, str) else existing.name
        )
        if not new_name:
            raise DomainError("AgentProfile.name é obrigatório e não pode ser vazio.")

        new_system_prompt = (
            system_prompt
            if isinstance(system_prompt, str)
            else existing.system_prompt
        )
        if not new_system_prompt or not new_system_prompt.strip():
            raise DomainError(
                "AgentProfile.system_prompt é obrigatório e não pode ser vazio."
            )

        new_skills = (
            skills_allowlist
            if skills_allowlist is not UNSET
            else existing.skills_allowlist
        )
        new_tools = (
            tools_allowlist
            if tools_allowlist is not UNSET
            else existing.tools_allowlist
        )
        new_mcp = (
            mcp_allowlist
            if mcp_allowlist is not UNSET
            else existing.mcp_allowlist
        )
        new_model_override = (
            model_override
            if model_override is not UNSET
            else existing.model_override
        )
        new_tier = tier if tier is not None else existing.tier
        if not (1 <= new_tier <= 4):
            raise DomainError("AgentProfile.tier deve estar entre 1 e 4.")

        updated = AgentProfile(
            id=existing.id,
            user_id=existing.user_id,
            name=new_name,
            slug=existing.slug,
            system_prompt=new_system_prompt,
            skills_allowlist=new_skills,
            tools_allowlist=new_tools,
            mcp_allowlist=new_mcp,
            tier=new_tier,
            model_override=new_model_override,
            is_active=existing.is_active,
            archived_at=existing.archived_at,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
        )
        return await self._repository.update(updated)
