"""Caso de uso: atualizar label de definição de campo CRM (v1)."""
from __future__ import annotations

from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import FieldDefinition, FieldType
from src.domain.shared.errors import DomainError


class UpdateCrmFieldDefinition:
    """Atualiza apenas o label; key/field_type/entity são imutáveis na v1."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        definition_id: str,
        label: str,
        field_type: FieldType | None = None,
        key: str | None = None,
    ) -> FieldDefinition | None:
        """Rejeita tentativa de mudar field_type/key; atualiza label.

        Returns:
            Definição atualizada, ou ``None`` se miss/cross-user.
        """
        if field_type is not None or key is not None:
            raise DomainError(
                "field_type e key são imutáveis após a criação da definição."
            )
        cleaned_label = label.strip() if label else ""
        if not cleaned_label:
            raise DomainError("label é obrigatório e não pode ser vazio.")
        return await self._repository.update_field_definition_label(
            user_id, definition_id, cleaned_label
        )
