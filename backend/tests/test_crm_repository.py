"""Testes de `PostgresCrmRepository` (CRM persistence + extend-crm-fields).

Requer `INTEGRATION_POSTGRES_URI` (ou use o mesmo Postgres de dev).
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import psycopg
import pytest

from src.domain.crm import (
    Contact,
    Deal,
    DealStage,
    FieldDefinition,
    FieldEntity,
    FieldType,
    Lead,
    Note,
    NoteSource,
)
from src.infrastructure.auth.schema import ensure_schema as ensure_auth_schema
from src.infrastructure.persistence.crm_schema import ensure_crm_schema

INTEGRATION_URI_ENV = "INTEGRATION_POSTGRES_URI"
pytestmark = pytest.mark.skipif(
    not os.environ.get(INTEGRATION_URI_ENV),
    reason=(
        f"Requer Postgres de teste real. Defina {INTEGRATION_URI_ENV} "
        "(ex.: postgresql://jeff_ia:jeff_ia@localhost:5436/jeff_ia)."
    ),
)


def _uri() -> str:
    return os.environ[INTEGRATION_URI_ENV]


@pytest.fixture(autouse=True)
def _setup_postgres() -> None:
    ensure_auth_schema(_uri())
    ensure_crm_schema(_uri())
    with psycopg.connect(_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE TABLE crm_notes, crm_deals, crm_contacts, "
                "crm_companies, crm_field_definitions, crm_leads CASCADE"
            )
        conn.commit()


def _insert_test_user() -> str:
    user_id = str(uuid.uuid4())
    with psycopg.connect(_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (id, username, password_hash) "
                "VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (user_id, f"crm-test-{user_id}", "x"),
            )
        conn.commit()
    return user_id


def _new_contact(user_id: str, **overrides: object) -> Contact:
    kwargs: dict[str, object] = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "name": "Ana Silva",
        "email": "ana@example.com",
        "phone": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    kwargs.update(overrides)
    return Contact(**kwargs)  # type: ignore[arg-type]


def _new_lead(user_id: str, **overrides: object) -> Lead:
    kwargs: dict[str, object] = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "name": "João Lead",
        "phone": "11999998888",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    kwargs.update(overrides)
    return Lead(**kwargs)  # type: ignore[arg-type]


async def test_get_contact_of_other_user_returns_none() -> None:
    """unit-1 (REQ-005): busca com user_id alheio → None."""
    from src.infrastructure.persistence.crm_repository import PostgresCrmRepository

    owner = _insert_test_user()
    other = _insert_test_user()
    repo = PostgresCrmRepository(_uri())
    contact = _new_contact(owner)

    await repo.create_contact(contact)

    assert await repo.get_contact(owner, contact.id) is not None
    assert await repo.get_contact(other, contact.id) is None


async def test_archive_contact_excluded_from_default_list() -> None:
    """unit-2 (REQ-004): arquivado some da list padrão; aparece com include_archived."""
    from src.infrastructure.persistence.crm_repository import PostgresCrmRepository

    user_id = _insert_test_user()
    repo = PostgresCrmRepository(_uri())
    contact = _new_contact(user_id)

    await repo.create_contact(contact)
    archived = await repo.archive_contact(user_id, contact.id)
    assert archived is not None
    assert archived.archived_at is not None

    default_list = await repo.list_contacts(user_id)
    assert all(c.id != contact.id for c in default_list)

    with_archived = await repo.list_contacts(user_id, include_archived=True)
    assert any(c.id == contact.id for c in with_archived)


async def test_list_contacts_search_filters_by_name() -> None:
    """REQ-002: list/search filtra por user_id e termo."""
    from src.infrastructure.persistence.crm_repository import PostgresCrmRepository

    user_id = _insert_test_user()
    other = _insert_test_user()
    repo = PostgresCrmRepository(_uri())

    await repo.create_contact(_new_contact(user_id, name="Ana Silva", email="a@x.com"))
    await repo.create_contact(
        _new_contact(user_id, name="Bruno Costa", email="b@x.com")
    )
    await repo.create_contact(
        _new_contact(other, name="Ana Outra", email="c@x.com")
    )

    results = await repo.list_contacts(user_id, query="ana")
    assert len(results) == 1
    assert results[0].name == "Ana Silva"


async def test_list_contacts_page_returns_items_and_total() -> None:
    """crm-ext-task-persistence-1-unit-1: page=1 page_size=2 com 5 contatos → 2 + total 5."""
    from src.infrastructure.persistence.crm_repository import PostgresCrmRepository

    user_id = _insert_test_user()
    repo = PostgresCrmRepository(_uri())
    for i in range(5):
        await repo.create_contact(
            _new_contact(
                user_id,
                name=f"Contact {i}",
                email=f"c{i}@example.com",
            )
        )

    page = await repo.list_contacts_page(user_id, page=1, page_size=2)
    assert len(page.items) == 2
    assert page.total == 5


async def test_archive_contact_cascades_notes_and_deals() -> None:
    """crm-ext-task-persistence-1-unit-2: archive contato arquiva note + deal vinculados."""
    from src.infrastructure.persistence.crm_repository import PostgresCrmRepository

    user_id = _insert_test_user()
    repo = PostgresCrmRepository(_uri())
    contact = _new_contact(user_id)
    await repo.create_contact(contact)

    deal = Deal(
        id=str(uuid.uuid4()),
        user_id=user_id,
        title="Opp",
        stage=DealStage.QUALIFIED,
        contact_id=contact.id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await repo.create_deal(deal)

    note = Note(
        id=str(uuid.uuid4()),
        user_id=user_id,
        body="follow-up",
        source=NoteSource.USER,
        contact_id=contact.id,
        created_at=datetime.now(UTC),
    )
    await repo.create_note(note)

    archived = await repo.archive_contact(user_id, contact.id)
    assert archived is not None
    assert archived.archived_at is not None

    assert await repo.list_deals(user_id) == []
    assert await repo.list_notes_for_contact(user_id, contact.id) == []

    deals_archived = await repo.list_deals(user_id, include_archived=True)
    assert any(d.id == deal.id and d.archived_at is not None for d in deals_archived)

    notes_archived = await repo.list_notes_for_contact(
        user_id, contact.id, include_archived=True
    )
    assert any(n.id == note.id and n.archived_at is not None for n in notes_archived)


async def test_get_contact_by_email_returns_match_case_insensitive() -> None:
    """email-client-imap-mvp-task-inbox-4-unit-1 (REQ-006): match exato
    case-insensitive entre `Contact.email` (do user) e o email procurado."""
    from src.infrastructure.persistence.crm_repository import PostgresCrmRepository

    user_id = _insert_test_user()
    other_user = _insert_test_user()
    repo = PostgresCrmRepository(_uri())

    owner_contact = _new_contact(user_id, email="jane@example.com")
    other_contact = _new_contact(other_user, email="jane@example.com")
    await repo.create_contact(owner_contact)
    await repo.create_contact(other_contact)

    matched = await repo.get_contact_by_email(user_id, "Jane@Example.com")
    assert matched is not None
    assert matched.id == owner_contact.id


async def test_get_contact_by_email_returns_none_when_no_match() -> None:
    """email-client-imap-mvp-task-inbox-4-unit-1 (REQ-006): sem match, None."""
    from src.infrastructure.persistence.crm_repository import PostgresCrmRepository

    user_id = _insert_test_user()
    repo = PostgresCrmRepository(_uri())
    await repo.create_contact(_new_contact(user_id, email="jane@example.com"))

    matched = await repo.get_contact_by_email(user_id, "unknown@other.com")
    assert matched is None


async def test_create_field_definition_rejects_duplicate_key() -> None:
    """crm-ext-task-persistence-1-unit-3: duplicata (user, entity, key) falha."""
    from src.domain.crm import DuplicateFieldDefinitionError
    from src.infrastructure.persistence.crm_repository import PostgresCrmRepository

    user_id = _insert_test_user()
    repo = PostgresCrmRepository(_uri())
    first = FieldDefinition(
        id=str(uuid.uuid4()),
        user_id=user_id,
        entity=FieldEntity.CONTACT,
        key="segmento",
        label="Segmento",
        field_type=FieldType.TEXT,
    )
    await repo.create_field_definition(first)

    second = FieldDefinition(
        id=str(uuid.uuid4()),
        user_id=user_id,
        entity=FieldEntity.CONTACT,
        key="segmento",
        label="Outro",
        field_type=FieldType.TEXT,
    )
    with pytest.raises(DuplicateFieldDefinitionError):
        await repo.create_field_definition(second)

    listed = await repo.list_field_definitions(user_id, entity=FieldEntity.CONTACT)
    assert len(listed) == 1
    assert listed[0].label == "Segmento"


async def test_convert_lead_creates_contact_company_deal_with_source_lead_id() -> None:
    """unit-1 (REQ-003): company_name novo -> 1 Contato + 1 Empresa + 1 Deal,
    todos com source_lead_id apontando para o lead."""
    from src.infrastructure.persistence.crm_repository import PostgresCrmRepository

    user_id = _insert_test_user()
    repo = PostgresCrmRepository(_uri())
    lead = _new_lead(user_id, company_name="Acme Ltda", email="joao@acme.com")
    await repo.create_lead(lead)

    result = await repo.convert_lead(lead)

    assert result.contact.name == lead.name
    assert result.contact.email == lead.email
    assert result.contact.source_lead_id == lead.id
    assert result.company is not None
    assert result.company.name == "Acme Ltda"
    assert result.company.source_lead_id == lead.id
    assert result.deal.stage == DealStage.QUALIFIED
    assert result.deal.source_lead_id == lead.id
    assert result.deal.contact_id == result.contact.id
    assert result.deal.company_id == result.company.id
    assert result.lead.converted_at is not None
    assert result.lead.converted_contact_id == result.contact.id
    assert result.lead.converted_company_id == result.company.id
    assert result.lead.converted_deal_id == result.deal.id

    companies = await repo.list_companies(user_id)
    assert len([c for c in companies if c.name == "Acme Ltda"]) == 1


async def test_convert_lead_reuses_existing_company() -> None:
    """unit-2 (REQ-003): company_name já existe -> reaproveita, sem duplicar."""
    from src.domain.crm import Company
    from src.infrastructure.persistence.crm_repository import PostgresCrmRepository

    user_id = _insert_test_user()
    repo = PostgresCrmRepository(_uri())
    existing_company = Company(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name="Acme Ltda",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await repo.create_company(existing_company)

    lead = _new_lead(user_id, company_name="acme ltda", email="joao@acme.com")
    await repo.create_lead(lead)

    result = await repo.convert_lead(lead)

    assert result.company is not None
    assert result.company.id == existing_company.id

    companies = await repo.list_companies(user_id)
    assert len([c for c in companies if c.name.lower() == "acme ltda"]) == 1


async def test_convert_lead_rolls_back_on_failure() -> None:
    """REQ-003: falha em qualquer etapa reverte tudo (sem registros parciais)."""
    import src.infrastructure.persistence.crm_repository as crm_repository_module
    from src.infrastructure.persistence.crm_repository import PostgresCrmRepository

    user_id = _insert_test_user()
    repo = PostgresCrmRepository(_uri())
    lead = _new_lead(user_id, company_name="Falha Ltda", email="joao@falha.com")
    await repo.create_lead(lead)

    original_lead_columns = crm_repository_module._LEAD_COLUMNS
    crm_repository_module._LEAD_COLUMNS = original_lead_columns + ", coluna_inexistente"
    try:
        with pytest.raises(Exception):
            await repo.convert_lead(lead)
    finally:
        crm_repository_module._LEAD_COLUMNS = original_lead_columns

    with psycopg.connect(_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM crm_contacts WHERE user_id = %s", (user_id,)
            )
            row = cur.fetchone()
            assert row is not None and row[0] == 0
            cur.execute(
                "SELECT count(*) FROM crm_companies WHERE user_id = %s", (user_id,)
            )
            row = cur.fetchone()
            assert row is not None and row[0] == 0
            cur.execute(
                "SELECT count(*) FROM crm_deals WHERE user_id = %s", (user_id,)
            )
            row = cur.fetchone()
            assert row is not None and row[0] == 0

    fresh = await repo.get_lead(user_id, lead.id)
    assert fresh is not None
    assert fresh.converted_at is None
