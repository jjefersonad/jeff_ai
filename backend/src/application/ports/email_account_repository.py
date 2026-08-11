"""Port de repositório de contas de email.

Abstrai a persistência de `EmailAccount` (Postgres no adapter) do restante
da camada de aplicação. Toda operação escopada a `user_id` é filtrada na
própria query (mesmo padrão de `CrmRepositoryPort`) — miss cross-user
retorna `None`, nunca exceção, para não revelar se a entrada existe
(REQ-002 do spec `email-account-management`).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.email import EmailAccount


class EmailAccountRepositoryPort(ABC):
    """Persiste `EmailAccount`, sempre escopada ao `user_id` dono da conta."""

    @abstractmethod
    async def create(self, account: EmailAccount) -> EmailAccount:
        """Insere a conta e devolve a linha persistida."""
        raise NotImplementedError

    @abstractmethod
    async def get(self, user_id: str, account_id: str) -> EmailAccount | None:
        """Retorna a conta do `user_id` ou `None` (miss ou cross-user)."""
        raise NotImplementedError

    @abstractmethod
    async def list_by_user(self, user_id: str) -> list[EmailAccount]:
        """Retorna as contas do `user_id`, ordenadas por criação."""
        raise NotImplementedError

    @abstractmethod
    async def list_all(self) -> list[EmailAccount]:
        """Retorna TODAS as contas, de todos os usuários.

        Uso restrito ao sync worker (`email-client-imap-mvp-task-sync-3`),
        que precisa varrer contas de todos os usuários para pollar as
        `is_active=true` — mesmo padrão de
        `UserIntegrationRepositoryPort.list_all`.
        """
        raise NotImplementedError

    @abstractmethod
    async def update(self, account: EmailAccount) -> EmailAccount | None:
        """Atualiza a conta própria; `None` se miss ou cross-user."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, user_id: str, account_id: str) -> bool:
        """Remove a conta própria; `True` se removida, `False` se miss/cross-user."""
        raise NotImplementedError
