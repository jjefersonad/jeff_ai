"""Caso de uso: listar leads CRM (REQ-002 lead-triage-pipeline)."""
from __future__ import annotations

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import Lead


class ListCrmLeads:
    """Lista leads do usuário; ativos (`converted_at IS NULL`) por default."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção."""
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        converted: bool = False,
    ) -> list[Lead]:
        """Retorna leads ativos, ou convertidos se `converted=True`."""
        return await self._repository.list_leads(user_id, converted=converted)
