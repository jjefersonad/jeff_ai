"""Caso de uso: listar estágios fixos do funil (REQ-001 crm-deals)."""
from __future__ import annotations

from src.domain.crm import DealStage, default_deal_stages


class ListCrmDealStages:
    """Expõe os estágios padrão do funil em ordem fixa."""

    async def execute(self) -> list[DealStage]:
        """Retorna lead → qualified → proposal → won → lost."""
        return default_deal_stages()
