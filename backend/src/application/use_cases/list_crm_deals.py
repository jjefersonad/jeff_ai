"""Caso de uso: listar deals CRM (REQ-004 crm-deals)."""
from __future__ import annotations

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Deal, DealStage


class ListCrmDeals:
    """Lista deals do usuário, com filtro opcional por estágio."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        stage: DealStage | None = None,
        include_archived: bool = False,
    ) -> list[Deal]:
        """Retorna só deals do `user_id`."""
        return await self._repository.list_deals(
            user_id,
            stage=stage,
            include_archived=include_archived,
        )
