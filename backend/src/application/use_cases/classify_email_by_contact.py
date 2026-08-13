"""Caso de uso: vincular email recebido a um deal ativo por contato.

REQ-005 (deal-pipeline-state-machine, `sales-pipeline-via-agent`).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Contact, Note, NoteSource


class ClassifyEmailByContact:
    """Grava uma nota de sistema no deal ativo do remetente, se houver.

    Apenas registra histórico — nunca move o estágio do deal (D-005 do
    design). Sem contato correspondente ou sem deal ativo (`stage NOT IN
    ('won','lost')`), não faz nada.
    """

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        sender_email: str,
        subject: str,
        contact: Contact | None = None,
    ) -> Note | None:
        """Cria a nota `source='system'` no deal ativo do remetente, se houver.

        `contact`, se já resolvido pelo chamador (ex.: o sync worker já
        chama `get_contact_by_email` para popular `emails.contact_id`), evita
        um segundo lookup idêntico — passe `None` para resolver aqui.
        """
        if contact is None:
            contact = await self._repository.get_contact_by_email(
                user_id, sender_email
            )
        if contact is None:
            return None
        deal = await self._repository.get_active_deal_by_contact(user_id, contact.id)
        if deal is None:
            return None
        note = Note(
            id=str(uuid.uuid4()),
            user_id=user_id,
            body=f"Email recebido: {subject}",
            source=NoteSource.SYSTEM,
            deal_id=deal.id,
            created_at=datetime.now(UTC),
        )
        return await self._repository.create_note(note)
