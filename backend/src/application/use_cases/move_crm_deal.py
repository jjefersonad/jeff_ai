"""Caso de uso: mover deal entre estágios (REQ-003 crm-deals)."""
from __future__ import annotations

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Deal, DealStage
from src.domain.shared.errors import DomainError


def _parse_stage(stage: DealStage | str) -> DealStage:
    if isinstance(stage, DealStage):
        return stage
    try:
        return DealStage(stage)
    except ValueError as exc:
        raise DomainError(f"stage inválido: {stage!r}") from exc


class MoveCrmDeal:
    """Move um deal próprio para um estágio válido do funil."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        deal_id: str,
        stage: DealStage | str,
    ) -> Deal | None:
        """Atualiza o estágio; ``None`` se miss / cross-user.

        Raises:
            DomainError: se `stage` não for um valor do funil.
        """
        resolved = _parse_stage(stage)
        return await self._repository.move_deal(user_id, deal_id, resolved)
