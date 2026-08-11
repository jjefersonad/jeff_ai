"""Caso de uso: buscar emails por texto (REQ-003 inbox-1)."""
from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.email_repository import EmailRepositoryPort
from src.domain.email import Email


@dataclass(frozen=True)
class SearchEmailsResult:
    """Envelope de resultado de busca de emails."""

    items: list[Email]
    query: str
    account_id: str | None


class SearchEmails:
    """Busca emails por texto em `subject`, `body_text` e `from_address`."""

    def __init__(self, *, repository: EmailRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self,
        user_id: str,
        query: str,
        account_id: str | None = None,
        limit: int = 20,
    ) -> SearchEmailsResult:
        """Busca emails do `user_id` com `account_id` opcional."""
        safe_limit = max(1, min(limit, 100))
        items = await self._repository.search(
            user_id=user_id,
            account_id=account_id,
            query=query,
            limit=safe_limit,
        )
        return SearchEmailsResult(
            items=items,
            query=query,
            account_id=account_id,
        )
