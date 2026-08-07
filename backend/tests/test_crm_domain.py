"""Testes do domínio CRM (`add-simple-crm-module-task-domain-1`).

Unit-1: DealStage order — lead → qualified → proposal → won → lost.
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
        DealStage.LEAD,
        DealStage.QUALIFIED,
        DealStage.PROPOSAL,
        DealStage.WON,
        DealStage.LOST,
    ]
    assert [s.value for s in default_deal_stages()] == [
        "lead",
        "qualified",
        "proposal",
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
