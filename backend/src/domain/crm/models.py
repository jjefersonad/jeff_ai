"""Domínio CRM: entidades, estágios do funil e fontes de nota.

PURO: zero import de framework. Persistência e HTTP ficam em
`infrastructure/`; regras de validação de use case (email/phone, alvo
único) vivem na aplicação — aqui só o modelo de dados de negócio.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class DealStage(str, Enum):
    """Estágios fixos do funil (REQ-001 crm-deals). Ordem = ordem do funil."""

    LEAD = "lead"
    QUALIFIED = "qualified"
    PROPOSAL = "proposal"
    WON = "won"
    LOST = "lost"


def default_deal_stages() -> list[DealStage]:
    """Lista ordenada dos estágios padrão do funil."""
    return list(DealStage)


class NoteSource(str, Enum):
    """Origem da nota (usuário na UI vs agente)."""

    USER = "user"
    AGENT = "agent"


class FieldEntity(str, Enum):
    """Entidade alvo de uma definição de campo personalizado."""

    CONTACT = "contact"
    COMPANY = "company"
    DEAL = "deal"


class FieldType(str, Enum):
    """Tipos permitidos de campo personalizado na v1."""

    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"


@dataclass
class FieldDefinition:
    """Definição de campo personalizado escopada a um `user_id`."""

    id: str
    user_id: str
    entity: FieldEntity
    key: str
    label: str
    field_type: FieldType
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Company:
    """Empresa/conta do CRM, escopada a um `user_id`."""

    id: str
    user_id: str
    name: str
    website: str | None = None
    domain: str | None = None
    phone: str | None = None
    notes: str | None = None
    city: str | None = None
    state: str | None = None
    custom_values: dict[str, Any] = field(default_factory=dict)
    archived_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Contact:
    """Pessoa/contato do CRM, escopada a um `user_id`."""

    id: str
    user_id: str
    name: str
    email: str | None = None
    phone: str | None = None
    company_id: str | None = None
    status: str | None = None
    tags: list[str] = field(default_factory=list)
    city: str | None = None
    state: str | None = None
    custom_values: dict[str, Any] = field(default_factory=dict)
    archived_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Deal:
    """Oportunidade no funil, escopada a um `user_id`."""

    id: str
    user_id: str
    title: str
    stage: DealStage = DealStage.LEAD
    value: Decimal | None = None
    currency: str | None = None
    contact_id: str | None = None
    company_id: str | None = None
    custom_values: dict[str, Any] = field(default_factory=dict)
    archived_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Note:
    """Nota imutável ligada a exatamente um alvo (contato, empresa ou deal)."""

    id: str
    user_id: str
    body: str
    source: NoteSource
    contact_id: str | None = None
    company_id: str | None = None
    deal_id: str | None = None
    archived_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
