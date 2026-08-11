"""Caso de uso: listar emails do user, com filtros opcionais (REQ-001 inbox-1)."""
from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.email_repository import EmailRepositoryPort
from src.domain.email import Email


@dataclass(frozen=True)
class ListEmailsResult:
    """Envelope paginado de emails para API/UI.

    `account_id`/`folder` são ecoados de volta como `None` quando a listagem
    não foi filtrada — facilita o frontend distinguir "unificado" de
    "filtrado por pasta X da conta Y".
    """

    items: list[Email]
    account_id: str | None
    folder: str | None


class ListEmails:
    """Lista emails do `user_id`, opcionalmente filtrados por `account_id`/`folder`."""

    def __init__(self, *, repository: EmailRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self,
        user_id: str,
        account_id: str | None = None,
        folder: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> ListEmailsResult:
        """Retorna página de emails do `user_id` (opcionalmente filtrada)."""
        safe_limit = max(1, min(limit, 100))
        safe_offset = max(0, offset)
        items = await self._repository.list_by_account(
            user_id=user_id,
            account_id=account_id,
            folder=folder,
            limit=safe_limit,
            offset=safe_offset,
        )
        return ListEmailsResult(
            items=items,
            account_id=account_id,
            folder=folder,
        )
