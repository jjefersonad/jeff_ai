"""Caso de uso: criar AgentProfile (REQ-001 do spec `agent-profile-crud`)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from src.application.ports.agent_profile_repository import (
    AgentProfileRepositoryPort,
)
from src.domain.agents import AgentProfile, DuplicateAgentProfileError
from src.domain.shared.errors import DomainError


class CreateAgentProfile:
    """Cria um AgentProfile escopado ao `user_id` autenticado."""

    def __init__(self, *, repository: AgentProfileRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        name: str,
        slug: str,
        system_prompt: str,
        skills_allowlist: list[str] | None = None,
        tools_allowlist: list[str] | None = None,
        tier: int = 1,
        model_override: str | None = None,
    ) -> AgentProfile:
        """Cria e persiste um AgentProfile; checa unicidade de `(user_id, slug)`.

        Raises:
            DomainError: se `name`/`system_prompt` estiver vazio, `slug`
                não estiver em kebab-case, ou `tier` estiver fora de `1..4`.
            DuplicateAgentProfileError: se já existir perfil ativo com o
                mesmo slug para esse `user_id`.
        """
        cleaned_name = name.strip() if name else ""
        if not cleaned_name:
            raise DomainError("AgentProfile.name é obrigatório e não pode ser vazio.")

        cleaned_slug = slug.strip() if slug else ""
        AgentProfile.validate_slug_format(cleaned_slug)

        if not (1 <= tier <= 4):
            raise DomainError("AgentProfile.tier deve estar entre 1 e 4.")

        if not system_prompt or not system_prompt.strip():
            raise DomainError(
                "AgentProfile.system_prompt é obrigatório e não pode ser vazio."
            )

        existing = await self._repository.get_by_slug(user_id, cleaned_slug)
        if existing is not None:
            raise DuplicateAgentProfileError(
                f"Já existe um agent_profile ativo com slug '{cleaned_slug}'."
            )

        now = datetime.now(UTC)
        profile = AgentProfile(
            id=str(uuid.uuid4()),
            user_id=user_id,
            name=cleaned_name,
            slug=cleaned_slug,
            system_prompt=system_prompt,
            skills_allowlist=skills_allowlist,
            tools_allowlist=tools_allowlist,
            tier=tier,
            model_override=model_override,
            is_active=True,
            archived_at=None,
            created_at=now,
            updated_at=now,
        )
        return await self._repository.create(profile)
