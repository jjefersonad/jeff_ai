"""Caso de uso: listar definições de campo personalizado CRM."""
from __future__ import annotations

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import FieldDefinition, FieldEntity


class ListCrmFieldDefinitions:
    """Lista definições do usuário da sessão."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        entity: FieldEntity | None = None,
    ) -> list[FieldDefinition]:
        """Retorna só definições do `user_id` (isolamento por sessão)."""
        return await self._repository.list_field_definitions(
            user_id, entity=entity
        )
