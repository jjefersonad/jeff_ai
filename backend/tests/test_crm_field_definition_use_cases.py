"""Testes dos use cases de field definitions + validate_custom_values.

crm-ext-task-usecases-1 units 1–3.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from crm_repository_fakes import CrmRepositoryPortExtensions
from src.application.ports.crm_repository import CrmRepositoryPort
from src.domain.crm import (
    Company,
    Contact,
    Deal,
    DealStage,
    DuplicateFieldDefinitionError,
    FieldDefinition,
    FieldEntity,
    FieldType,
    Note,
)
from src.domain.shared.errors import DomainError


class _FakeCrmRepository(CrmRepositoryPortExtensions, CrmRepositoryPort):
    def __init__(self) -> None:
        self.definitions: dict[str, FieldDefinition] = {}

    async def create_company(self, company: Company) -> Company:
        raise NotImplementedError

    async def get_company(self, user_id: str, company_id: str) -> Company | None:
        return None

    async def list_companies(
        self,
        user_id: str,
        *,
        query: str | None = None,
        include_archived: bool = False,
    ) -> list[Company]:
        return []

    async def update_company(self, company: Company) -> Company | None:
        return None

    async def archive_company(self, user_id: str, company_id: str) -> Company | None:
        return None

    async def create_contact(self, contact: Contact) -> Contact:
        raise NotImplementedError

    async def get_contact(self, user_id: str, contact_id: str) -> Contact | None:
        return None

    async def list_contacts(
        self,
        user_id: str,
        *,
        query: str | None = None,
        company_id: str | None = None,
        include_archived: bool = False,
    ) -> list[Contact]:
        return []

    async def update_contact(self, contact: Contact) -> Contact | None:
        return None

    async def archive_contact(self, user_id: str, contact_id: str) -> Contact | None:
        return None

    async def create_deal(self, deal: Deal) -> Deal:
        raise NotImplementedError

    async def get_deal(self, user_id: str, deal_id: str) -> Deal | None:
        return None

    async def list_deals(
        self,
        user_id: str,
        *,
        stage: DealStage | None = None,
        include_archived: bool = False,
    ) -> list[Deal]:
        return []

    async def update_deal(self, deal: Deal) -> Deal | None:
        return None

    async def archive_deal(self, user_id: str, deal_id: str) -> Deal | None:
        return None

    async def move_deal(
        self, user_id: str, deal_id: str, stage: DealStage
    ) -> Deal | None:
        return None

    async def create_note(self, note: Note) -> Note:
        raise NotImplementedError

    async def list_notes_for_contact(
        self,
        user_id: str,
        contact_id: str,
        *,
        include_archived: bool = False,
    ) -> list[Note]:
        return []

    async def list_notes_for_company(
        self,
        user_id: str,
        company_id: str,
        *,
        include_archived: bool = False,
    ) -> list[Note]:
        return []

    async def list_notes_for_deal(
        self,
        user_id: str,
        deal_id: str,
        *,
        include_archived: bool = False,
    ) -> list[Note]:
        return []

    async def create_field_definition(
        self, definition: FieldDefinition
    ) -> FieldDefinition:
        for existing in self.definitions.values():
            if (
                existing.user_id == definition.user_id
                and existing.entity == definition.entity
                and existing.key == definition.key
            ):
                raise DuplicateFieldDefinitionError("duplicate")
        self.definitions[definition.id] = definition
        return definition

    async def list_field_definitions(
        self,
        user_id: str,
        *,
        entity: FieldEntity | None = None,
    ) -> list[FieldDefinition]:
        items = [d for d in self.definitions.values() if d.user_id == user_id]
        if entity is not None:
            items = [d for d in items if d.entity == entity]
        return items

    async def update_field_definition_label(
        self, user_id: str, definition_id: str, label: str
    ) -> FieldDefinition | None:
        definition = self.definitions.get(definition_id)
        if definition is None or definition.user_id != user_id:
            return None
        updated = FieldDefinition(
            id=definition.id,
            user_id=definition.user_id,
            entity=definition.entity,
            key=definition.key,
            label=label,
            field_type=definition.field_type,
            created_at=definition.created_at,
            updated_at=datetime.now(UTC),
        )
        self.definitions[definition_id] = updated
        return updated


async def test_create_field_definition_persists_for_session_user() -> None:
    """unit-1: CreateCrmFieldDefinition persiste e aparece no list."""
    from src.application.use_cases.create_crm_field_definition import (
        CreateCrmFieldDefinition,
    )
    from src.application.use_cases.list_crm_field_definitions import (
        ListCrmFieldDefinitions,
    )

    repo = _FakeCrmRepository()
    created = await CreateCrmFieldDefinition(repository=repo).execute(
        user_id="user-a",
        entity=FieldEntity.CONTACT,
        key="segmento",
        label="Segmento",
        field_type=FieldType.TEXT,
    )
    assert created.user_id == "user-a"
    assert created.key == "segmento"

    listed = await ListCrmFieldDefinitions(repository=repo).execute(
        user_id="user-a", entity=FieldEntity.CONTACT
    )
    assert len(listed) == 1
    assert listed[0].id == created.id

    other = await ListCrmFieldDefinitions(repository=repo).execute(user_id="user-b")
    assert other == []


async def test_validate_custom_values_rejects_unknown_and_bad_type() -> None:
    """unit-2: chave sem def / number=\"abc\" → DomainError; text ok."""
    from src.application.use_cases.crm_custom_values import validate_custom_values

    definitions = [
        FieldDefinition(
            id=str(uuid.uuid4()),
            user_id="u1",
            entity=FieldEntity.CONTACT,
            key="segmento",
            label="Segmento",
            field_type=FieldType.TEXT,
        ),
        FieldDefinition(
            id=str(uuid.uuid4()),
            user_id="u1",
            entity=FieldEntity.CONTACT,
            key="ticket",
            label="Ticket",
            field_type=FieldType.NUMBER,
        ),
    ]

    merged = validate_custom_values(
        definitions=definitions,
        existing={"segmento": "old"},
        incoming={"segmento": "PME"},
    )
    assert merged == {"segmento": "PME"}

    with pytest.raises(DomainError, match="definição"):
        validate_custom_values(
            definitions=definitions,
            existing={},
            incoming={"foo": "x"},
        )

    with pytest.raises(DomainError, match="number|tipo"):
        validate_custom_values(
            definitions=definitions,
            existing={},
            incoming={"ticket": "abc"},
        )


async def test_update_field_definition_rejects_type_change_allows_label() -> None:
    """unit-3: field_type imutável; label-only update ok."""
    from src.application.use_cases.create_crm_field_definition import (
        CreateCrmFieldDefinition,
    )
    from src.application.use_cases.update_crm_field_definition import (
        UpdateCrmFieldDefinition,
    )

    repo = _FakeCrmRepository()
    created = await CreateCrmFieldDefinition(repository=repo).execute(
        user_id="user-a",
        entity=FieldEntity.DEAL,
        key="prazo",
        label="Prazo",
        field_type=FieldType.TEXT,
    )

    with pytest.raises(DomainError, match="field_type|imutáv"):
        await UpdateCrmFieldDefinition(repository=repo).execute(
            user_id="user-a",
            definition_id=created.id,
            label="Prazo novo",
            field_type=FieldType.NUMBER,
        )

    updated = await UpdateCrmFieldDefinition(repository=repo).execute(
        user_id="user-a",
        definition_id=created.id,
        label="Prazo contratual",
    )
    assert updated is not None
    assert updated.label == "Prazo contratual"
    assert updated.field_type is FieldType.TEXT
    assert updated.key == "prazo"
