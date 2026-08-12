"""Testes do domínio CRM (`add-simple-crm-module-task-domain-1`).

Unit-1: DealStage order — qualified → proposal → negotiation → won → lost
(`sales-pipeline-via-agent`: `lead` deixou de ser estágio de deal).
"""
from __future__ import annotations

import ast
from pathlib import Path

from src.domain.crm import (
    Company,
    Contact,
    Deal,
    DealStage,
    Note,
    NoteSource,
    default_deal_stages,
)


def test_default_deal_stages_order() -> None:
    """WHEN o código lista os estágios padrão THEN ordem fixa da spec."""
    assert default_deal_stages() == [
        DealStage.QUALIFIED,
        DealStage.PROPOSAL,
        DealStage.NEGOTIATION,
        DealStage.WON,
        DealStage.LOST,
    ]
    assert [s.value for s in default_deal_stages()] == [
        "qualified",
        "proposal",
        "negotiation",
        "won",
        "lost",
    ]


def test_deal_stage_values_match_enum_definition_order() -> None:
    assert list(DealStage) == default_deal_stages()


def test_crm_domain_modules_do_not_import_frameworks() -> None:
    domain_dir = Path(__file__).parent.parent / "src" / "domain" / "crm"
    forbidden = ("fastapi", "psycopg", "sqlalchemy", "langgraph", "langchain")
    for path in domain_dir.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(f in alias.name.lower() for f in forbidden), path
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not any(f in node.module.lower() for f in forbidden), path


def test_entities_are_importable() -> None:
    assert Contact.__name__ == "Contact"
    assert Company.__name__ == "Company"
    assert Deal.__name__ == "Deal"
    assert Note.__name__ == "Note"
    assert NoteSource.USER.value == "user"
    assert NoteSource.AGENT.value == "agent"


def test_contact_and_company_expose_location_and_custom_values() -> None:
    """crm-ext-task-domain-1-unit-1: city/state/custom_values nas entidades."""
    contact = Contact(
        id="c1",
        user_id="u1",
        name="Ana",
        email="ana@ex.com",
        city="São Paulo",
        state="SP",
        custom_values={"segmento": "PME"},
    )
    company = Company(
        id="co1",
        user_id="u1",
        name="Acme",
        city="Rio",
        state="RJ",
        custom_values={"porte": "grande"},
    )
    deal = Deal(
        id="d1",
        user_id="u1",
        title="Proposta",
        custom_values={"prazo_contrato": "12m"},
    )

    assert contact.city == "São Paulo"
    assert contact.state == "SP"
    assert contact.custom_values == {"segmento": "PME"}
    assert company.city == "Rio"
    assert company.state == "RJ"
    assert company.custom_values == {"porte": "grande"}
    assert deal.custom_values == {"prazo_contrato": "12m"}


def test_field_definition_and_enums_v1() -> None:
    """crm-ext-task-domain-1-unit-1: FieldDefinition + FieldType/FieldEntity."""
    from src.domain.crm import FieldDefinition, FieldEntity, FieldType

    definition = FieldDefinition(
        id="f1",
        user_id="u1",
        entity=FieldEntity.CONTACT,
        key="segmento",
        label="Segmento",
        field_type=FieldType.TEXT,
    )
    assert definition.key == "segmento"
    assert definition.label == "Segmento"
    assert definition.field_type is FieldType.TEXT
    assert definition.entity is FieldEntity.CONTACT
    assert {t.value for t in FieldType} == {"text", "number", "boolean"}
    assert {e.value for e in FieldEntity} == {"contact", "company", "deal"}


def test_note_optional_archived_at() -> None:
    note = Note(
        id="n1",
        user_id="u1",
        body="oi",
        source=NoteSource.USER,
        contact_id="c1",
    )
    assert note.archived_at is None

