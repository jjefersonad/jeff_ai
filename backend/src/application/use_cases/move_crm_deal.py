"""Caso de uso: mover deal entre estágios.

REQ-003 (crm-deals) + REQ-002/REQ-004 (deal-pipeline-state-machine).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Deal, DealStage, Note, NoteSource
from src.domain.shared.errors import DomainError


def _parse_stage(stage: DealStage | str) -> DealStage:
    if isinstance(stage, DealStage):
        return stage
    try:
        return DealStage(stage)
    except ValueError as exc:
        raise DomainError(f"stage inválido: {stage!r}") from exc


class MoveCrmDeal:
    """Move um deal próprio para um estágio válido do funil.

    Toda transição bem-sucedida grava `crm_notes(deal_id, body='<de> → <para>',
    source=<origem>)` como histórico (REQ-004 deal-pipeline-state-machine) —
    sem tabela de log dedicada, sem validação de grafo de transições (REQ-002).
    """

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        deal_id: str,
        stage: DealStage | str,
        source: NoteSource,
    ) -> Deal | None:
        """Atualiza o estágio e grava a nota de transição; ``None`` se miss / cross-user.

        Raises:
            DomainError: se `stage` não for um valor do funil.
        """
        resolved = _parse_stage(stage)
        existing = await self._repository.get_deal(user_id, deal_id)
        if existing is None:
            return None
        # Capturado ANTES de mover: `existing` pode ser o mesmo objeto que
        # `move_deal` muta (fakes de teste in-memory) — ler `.stage` depois
        # da mutação pegaria o estágio novo, não o antigo.
        previous_stage = existing.stage
        moved = await self._repository.move_deal(user_id, deal_id, resolved)
        if moved is None:
            return None
        await self._repository.create_note(
            Note(
                id=str(uuid.uuid4()),
                user_id=user_id,
                body=f"{previous_stage.value} → {resolved.value}",
                source=source,
                deal_id=deal_id,
                created_at=datetime.now(UTC),
            )
        )
        return moved
