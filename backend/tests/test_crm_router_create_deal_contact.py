"""POST /api/crm/deals nested contact (backend-create-2)."""
from __future__ import annotations

from src.application.use_cases.create_crm_field_definition import (
    CreateCrmFieldDefinition,
)
from src.domain.crm import FieldDefinition, FieldEntity, FieldType
from test_crm_router_notes_deals import _FakeCrmRepository as _BaseFake
from test_crm_router_notes_deals import _client


class _FakeCrmRepository(_BaseFake):
    def __init__(self) -> None:
        super().__init__()
        self.definitions: dict[str, FieldDefinition] = {}

    async def create_field_definition(
        self, definition: FieldDefinition
    ) -> FieldDefinition:
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


def test_post_deal_with_nested_contact_email_creates_both() -> None:
    """unit-1: POST title + contact.email → 201, deal and contact linked."""
    repo = _FakeCrmRepository()
    response = _client(repo).post(
        "/api/crm/deals",
        json={
            "title": "Acme",
            "contact": {"email": "joao@acme.com"},
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["contact_id"] is not None
    contact = repo.contacts[body["contact_id"]]
    assert contact.email == "joao@acme.com"
    assert len(repo.deals) == 1
    assert len(repo.contacts) == 1


def test_post_deal_title_only_has_null_contact_id() -> None:
    """unit-2: POST only title → 201, contact_id null."""
    repo = _FakeCrmRepository()
    response = _client(repo).post("/api/crm/deals", json={"title": "Acme"})
    assert response.status_code == 201
    body = response.json()
    assert body["contact_id"] is None
    assert repo.contacts == {}


def test_post_deal_contact_without_identifier_returns_422() -> None:
    """unit-3: POST contact.name without email/phone → 422, no deal."""
    repo = _FakeCrmRepository()
    response = _client(repo).post(
        "/api/crm/deals",
        json={"title": "Acme", "contact": {"name": "João"}},
    )
    assert response.status_code == 422
    assert repo.deals == {}
    assert repo.contacts == {}


async def test_post_deal_splits_contact_and_deal_custom_values() -> None:
    """unit-4: top-level custom_values → deal; nested → contact."""
    repo = _FakeCrmRepository()
    await CreateCrmFieldDefinition(repository=repo).execute(
        user_id="user-a",
        entity=FieldEntity.CONTACT,
        key="segmento",
        label="Segmento",
        field_type=FieldType.TEXT,
    )
    await CreateCrmFieldDefinition(repository=repo).execute(
        user_id="user-a",
        entity=FieldEntity.DEAL,
        key="ticket_medio",
        label="Ticket médio",
        field_type=FieldType.NUMBER,
    )
    response = _client(repo).post(
        "/api/crm/deals",
        json={
            "title": "Acme",
            "custom_values": {"ticket_medio": 1500},
            "contact": {
                "email": "joao@acme.com",
                "custom_values": {"segmento": "PME"},
            },
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["custom_values"] == {"ticket_medio": 1500}
    contact = repo.contacts[body["contact_id"]]
    assert contact.custom_values == {"segmento": "PME"}
    deal = repo.deals[body["id"]]
    assert deal.custom_values == {"ticket_medio": 1500}


def test_patch_deal_updates_title() -> None:
    """PATCH /api/crm/deals/{id} altera o título."""
    repo = _FakeCrmRepository()
    client = _client(repo)
    created = client.post("/api/crm/deals", json={"title": "Acme"})
    deal_id = created.json()["id"]
    response = client.patch(f"/api/crm/deals/{deal_id}", json={"title": "Acme 2"})
    assert response.status_code == 200
    assert response.json()["title"] == "Acme 2"
    assert repo.deals[deal_id].title == "Acme 2"
