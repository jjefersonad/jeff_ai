"""Port de repositório de perfis de agente.

Abstrai a persistência de `AgentProfile` (Postgres no adapter) do restante
da camada de aplicação. Toda operação escopada a `user_id` é filtrada na
própria query (mesmo padrão de `EmailAccountRepositoryPort` e `CrmRepositoryPort`)
— miss cross-user retorna `None`, nunca exceção, para não revelar se a
entrada existe (REQ-007 do spec `agent-profile-crud`).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.agents import AgentProfile


class AgentProfileRepositoryPort(ABC):
    """Persiste `AgentProfile`, sempre escopada ao `user_id` dono."""

    @abstractmethod
    async def create(self, profile: AgentProfile) -> AgentProfile:
        """Insere o perfil e devolve a linha persistida."""
        raise NotImplementedError

    @abstractmethod
    async def get(self, user_id: str, profile_id: str) -> AgentProfile | None:
        """Retorna o perfil do `user_id` ou `None` (miss ou cross-user)."""
        raise NotImplementedError

    @abstractmethod
    async def get_by_slug(self, user_id: str, slug: str) -> AgentProfile | None:
        """Retorna o perfil ativo (não arquivado) do `user_id` pelo slug.

        Usado para checar unicidade antes de criar (mesma lógica do unique
        constraint no DB — defesa em profundidade). Retorna `None` se não
        existir ou se estiver arquivado.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_default(self, user_id: str) -> AgentProfile | None:
        """Retorna o perfil default do user (placeholder até `multi-agent-profiles-runtime`).

        Critério atual: o perfil ativo mais antigo (`created_at ASC LIMIT 1`).
        `None` se o user não tiver perfis ativos.
        """
        raise NotImplementedError

    @abstractmethod
    async def list_by_user(
        self, user_id: str, *, include_archived: bool = False
    ) -> list[AgentProfile]:
        """Retorna os perfis do `user_id`, ordenados por criação ASC.

        Por padrão exclui arquivados; `include_archived=True` inclui.
        """
        raise NotImplementedError

    @abstractmethod
    async def update(self, profile: AgentProfile) -> AgentProfile | None:
        """Atualiza o perfil próprio; `None` se miss ou cross-user."""
        raise NotImplementedError

    @abstractmethod
    async def archive(self, user_id: str, profile_id: str) -> AgentProfile | None:
        """Soft-delete: set `is_active=False`, `archived_at=now`. Idempotente?"""
        raise NotImplementedError
