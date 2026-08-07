"""Caso de uso: criar nota CRM (REQ-001 crm-notes).

Notas são imutáveis após criação — não há use case de update (REQ-003).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Note, NoteSource
from src.domain.shared.errors import DomainError


class CreateCrmNote:
    """Cria uma nota com exatamente um alvo pertencente ao usuário."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        body: str,
        source: NoteSource,
        contact_id: str | None = None,
        company_id: str | None = None,
        deal_id: str | None = None,
    ) -> Note:
        """Valida alvo único + ownership e persiste a nota.

        Raises:
            DomainError: body vazio, 0/2+ alvos, ou alvo inexistente/alheio.
        """
        cleaned_body = body.strip() if body else ""
        if not cleaned_body:
            raise DomainError("Note.body é obrigatório e não pode ser vazio.")

        targets = [
            ("contact_id", contact_id),
            ("company_id", company_id),
            ("deal_id", deal_id),
        ]
        provided = [(name, value) for name, value in targets if value]
        if len(provided) != 1:
            raise DomainError(
                "Note exige exatamente um alvo (contact_id, company_id ou deal_id)."
            )

        target_name, target_id = provided[0]
        assert target_id is not None
        if target_name == "contact_id":
            if await self._repository.get_contact(user_id, target_id) is None:
                raise DomainError("contact_id inválido para este usuário.")
        elif target_name == "company_id":
            if await self._repository.get_company(user_id, target_id) is None:
                raise DomainError("company_id inválido para este usuário.")
        else:
            if await self._repository.get_deal(user_id, target_id) is None:
                raise DomainError("deal_id inválido para este usuário.")

        note = Note(
            id=str(uuid.uuid4()),
            user_id=user_id,
            body=cleaned_body,
            source=source,
            contact_id=contact_id,
            company_id=company_id,
            deal_id=deal_id,
            created_at=datetime.now(UTC),
        )
        return await self._repository.create_note(note)
