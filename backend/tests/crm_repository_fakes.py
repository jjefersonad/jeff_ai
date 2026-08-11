"""Mixins stubs para fakes de `CrmRepositoryPort` nos testes unitários."""
from __future__ import annotations

from src.application.ports.crm_repository import ContactPage
from src.domain.crm import Contact, FieldDefinition, FieldEntity


class CrmRepositoryPortExtensions:
    """Implementações mínimas dos métodos novos do port (extend-crm-fields)."""

    async def list_contacts_page(
        self,
        user_id: str,
        *,
        query: str | None = None,
        company_id: str | None = None,
        include_archived: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> ContactPage:
        items = await self.list_contacts(  # type: ignore[attr-defined]
            user_id,
            query=query,
            company_id=company_id,
            include_archived=include_archived,
        )
        start = (max(1, page) - 1) * max(1, page_size)
        return ContactPage(
            items=items[start : start + page_size],
            total=len(items),
        )

    async def create_field_definition(
        self, definition: FieldDefinition
    ) -> FieldDefinition:
        raise NotImplementedError

    async def list_field_definitions(
        self,
        user_id: str,
        *,
        entity: FieldEntity | None = None,
    ) -> list[FieldDefinition]:
        return []

    async def update_field_definition_label(
        self, user_id: str, definition_id: str, label: str
    ) -> FieldDefinition | None:
        return None

    async def get_contact_by_email(
        self, user_id: str, email: str
    ) -> Contact | None:
        """Default: sem match — testes que precisam de comportamento sobrescrevem."""
        return None
