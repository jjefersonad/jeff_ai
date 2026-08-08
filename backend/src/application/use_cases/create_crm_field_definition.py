"""Caso de uso: criar definição de campo personalizado CRM."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from src.application.ports.crm_repository import CrmRepositoryPort
from src.application.use_cases.crm_custom_values import validate_field_key
from src.domain.crm import (
    DuplicateFieldDefinitionError,
    FieldDefinition,
    FieldEntity,
    FieldType,
)
from src.domain.shared.errors import DomainError


class CreateCrmFieldDefinition:
    """Cria definição escopada ao `user_id` da sessão."""

    def __init__(self, *, repository: CrmRepositoryPort) -> None:
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        entity: FieldEntity,
        key: str,
        label: str,
        field_type: FieldType,
    ) -> FieldDefinition:
        """Valida key/label e persiste; duplicata → DomainError."""
        cleaned_key = validate_field_key(key)
        cleaned_label = label.strip() if label else ""
        if not cleaned_label:
            raise DomainError("label é obrigatório e não pode ser vazio.")

        now = datetime.now(UTC)
        definition = FieldDefinition(
            id=str(uuid.uuid4()),
            user_id=user_id,
            entity=entity,
            key=cleaned_key,
            label=cleaned_label,
            field_type=field_type,
            created_at=now,
            updated_at=now,
        )
        try:
            return await self._repository.create_field_definition(definition)
        except DuplicateFieldDefinitionError as exc:
            raise DomainError(
                f"já existe definição {entity.value}/{cleaned_key} para este usuário."
            ) from exc
