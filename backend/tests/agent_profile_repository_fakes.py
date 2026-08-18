"""Fake in-memory de `AgentProfileRepositoryPort` para testes unitários."""
from __future__ import annotations

from datetime import UTC, datetime

from src.application.ports.agent_profile_repository import (
    AgentProfileRepositoryPort,
)
from src.domain.agents import AgentProfile


class InMemoryAgentProfileRepository(AgentProfileRepositoryPort):
    """Persistência em memória, escopada por `user_id`.

    Implementa todos os métodos do port respeitando o contrato:
    - `user_id` filtra em todas as queries
    - miss cross-user retorna `None` ou lista vazia
    - `get_by_slug` só retorna perfis ativos (não arquivados)
    - `archive` é idempotente (segunda chamada retorna `None`)
    """

    def __init__(self) -> None:
        self._by_id: dict[str, AgentProfile] = {}

    async def create(self, profile: AgentProfile) -> AgentProfile:
        self._by_id[profile.id] = profile
        return profile

    async def get(
        self, user_id: str, profile_id: str
    ) -> AgentProfile | None:
        p = self._by_id.get(profile_id)
        if p is None or p.user_id != user_id:
            return None
        return p

    async def get_by_slug(
        self, user_id: str, slug: str
    ) -> AgentProfile | None:
        for p in self._by_id.values():
            if (
                p.user_id == user_id
                and p.slug == slug
                and p.archived_at is None
            ):
                return p
        return None

    async def get_default(self, user_id: str) -> AgentProfile | None:
        actives = [
            p
            for p in self._by_id.values()
            if p.user_id == user_id and p.is_active and p.archived_at is None
        ]
        if not actives:
            return None
        return sorted(actives, key=lambda p: p.created_at)[0]

    async def list_by_user(
        self, user_id: str, *, include_archived: bool = False
    ) -> list[AgentProfile]:
        result = [
            p
            for p in self._by_id.values()
            if p.user_id == user_id
            and (include_archived or p.archived_at is None)
        ]
        return sorted(result, key=lambda p: p.created_at)

    async def update(self, profile: AgentProfile) -> AgentProfile | None:
        existing = self._by_id.get(profile.id)
        if existing is None or existing.user_id != profile.user_id:
            return None
        self._by_id[profile.id] = profile
        return profile

    async def archive(
        self, user_id: str, profile_id: str
    ) -> AgentProfile | None:
        existing = self._by_id.get(profile_id)
        if existing is None or existing.user_id != user_id:
            return None
        archived = AgentProfile(
            id=existing.id,
            user_id=existing.user_id,
            name=existing.name,
            slug=existing.slug,
            system_prompt=existing.system_prompt,
            skills_allowlist=existing.skills_allowlist,
            tools_allowlist=existing.tools_allowlist,
            tier=existing.tier,
            model_override=existing.model_override,
            is_active=False,
            archived_at=datetime.now(UTC),
            created_at=existing.created_at,
            updated_at=existing.updated_at,
        )
        self._by_id[profile_id] = archived
        return archived
