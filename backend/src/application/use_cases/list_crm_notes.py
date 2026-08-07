"""Caso de uso: listar notas CRM por alvo (REQ-002 crm-notes)."""
from __future__ import annotations

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Note
from src.domain.shared.errors import DomainError


class ListCrmNotes:
    """Lista notas de um alvo, mais recente primeiro."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        contact_id: str | None = None,
        company_id: str | None = None,
        deal_id: str | None = None,
    ) -> list[Note]:
        """Retorna notas do alvo; exige exatamente um alvo.

        Raises:
            DomainError: se 0 ou 2+ alvos forem informados.
        """
        targets = [
            ("contact", contact_id),
            ("company", company_id),
            ("deal", deal_id),
        ]
        provided = [(kind, value) for kind, value in targets if value]
        if len(provided) != 1:
            raise DomainError(
                "Listagem de notas exige exatamente um alvo "
                "(contact_id, company_id ou deal_id)."
            )
        kind, target_id = provided[0]
        assert target_id is not None
        if kind == "contact":
            return await self._repository.list_notes_for_contact(user_id, target_id)
        if kind == "company":
            return await self._repository.list_notes_for_company(user_id, target_id)
        return await self._repository.list_notes_for_deal(user_id, target_id)
