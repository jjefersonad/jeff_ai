"""Caso de uso: buscar um email por id, marcando-o como lido (REQ-002 inbox-1)."""
from __future__ import annotations

from src.application.ports.email_repository import EmailRepositoryPort
from src.domain.email import Email


class GetEmail:
    """Retorna um email pelo id, ou `None` se não existe ou não é do user.

    Marcar como lido é efeito colateral obrigatório (REQ-002 do spec
    `email-inbox`): o caller da UI recebe `body_html`/`body_text` exatamente
    uma vez, e a próxima listagem vê `is_read=true`.
    """

    def __init__(self, *, repository: EmailRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(self, user_id: str, email_id: str) -> Email | None:
        """Retorna o email do `user_id` ou `None` (miss ou cross-user).

        Side effect: marca `is_read=true` quando o email existe. `mark_read`
        é uma no-op silenciosa em miss/cross-user — não revela se a linha
        existe (mesma regra de `EmailRepositoryPort.get`).
        """
        email = await self._repository.get(user_id=user_id, email_id=email_id)
        if email is None:
            return None
        await self._repository.mark_read(user_id=user_id, email_id=email_id)
        return email
