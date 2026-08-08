"""Domínio CRM — entidades e estágios do funil.

PURO: zero import de framework. Persistência e HTTP ficam em
`infrastructure/`.
"""
from src.domain.crm.errors import DuplicateFieldDefinitionError
from src.domain.crm.models import (
    Company,
    Contact,
    Deal,
    DealStage,
    FieldDefinition,
    FieldEntity,
    FieldType,
    Note,
    NoteSource,
    default_deal_stages,
)

__all__ = [
    "Company",
    "Contact",
    "Deal",
    "DealStage",
    "DuplicateFieldDefinitionError",
    "FieldDefinition",
    "FieldEntity",
    "FieldType",
    "Note",
    "NoteSource",
    "default_deal_stages",
]
