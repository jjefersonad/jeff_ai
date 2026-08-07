"""Tools CRM (`crm_*`): search/upsert contact, add note, list/create/move deals.

Controllers finos sobre os use cases em `application/use_cases/crm_*`. Ownership
vem só de `resolve_user_id()` da sessão do run — parâmetro `user_id` do modelo,
se presente, é ignorado (REQ-003 crm-agent-access).

Notas criadas pelo agente usam sempre `source=agent`.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from langchain_core.tools import tool

from src.composition.dependencies import (
    build_create_crm_contact,
    build_create_crm_deal,
    build_create_crm_note,
    build_list_crm_contacts,
    build_list_crm_deals,
    build_move_crm_deal,
    build_update_crm_contact,
)
from src.domain.crm import Contact, Deal, DealStage, Note, NoteSource
from src.domain.shared.errors import DomainError
from src.infrastructure.ownership.store import resolve_user_id

_NO_IDENTITY = (
    "Identidade do usuário não resolvida para esta sessão; "
    "não é possível acessar o CRM."
)


async def _require_user_id() -> str | dict[str, str]:
    """Resolve o user_id da sessão ou devolve dict de erro."""
    user_id = await resolve_user_id()
    if not user_id:
        return {"error": _NO_IDENTITY}
    return user_id


def _contact_dict(contact: Contact) -> dict[str, Any]:
    return {
        "id": contact.id,
        "user_id": contact.user_id,
        "name": contact.name,
        "email": contact.email,
        "phone": contact.phone,
        "company_id": contact.company_id,
        "status": contact.status,
        "tags": list(contact.tags),
        "archived_at": contact.archived_at.isoformat() if contact.archived_at else None,
        "created_at": contact.created_at.isoformat(),
        "updated_at": contact.updated_at.isoformat(),
    }


def _deal_dict(deal: Deal) -> dict[str, Any]:
    return {
        "id": deal.id,
        "user_id": deal.user_id,
        "title": deal.title,
        "stage": deal.stage.value if isinstance(deal.stage, DealStage) else deal.stage,
        "value": str(deal.value) if deal.value is not None else None,
        "currency": deal.currency,
        "contact_id": deal.contact_id,
        "company_id": deal.company_id,
        "archived_at": deal.archived_at.isoformat() if deal.archived_at else None,
        "created_at": deal.created_at.isoformat(),
        "updated_at": deal.updated_at.isoformat(),
    }


def _note_dict(note: Note) -> dict[str, Any]:
    return {
        "id": note.id,
        "user_id": note.user_id,
        "body": note.body,
        "source": note.source.value if isinstance(note.source, NoteSource) else note.source,
        "contact_id": note.contact_id,
        "company_id": note.company_id,
        "deal_id": note.deal_id,
        "created_at": note.created_at.isoformat(),
    }


@tool
async def crm_search_contacts(
    query: str | None = None,
    company_id: str | None = None,
    user_id: str | None = None,
) -> list[dict[str, Any]] | dict[str, Any]:
    """[CRM Jeff AI] `crm_search_contacts` — busca/lista contatos do CRM nativo.

    Módulo Jeff AI (`/crm`, Postgres). NÃO confundir com MCP externo
    (`contacts_list_contacts`, `lead_gen_*`, etc.). `query` filtra por nome,
    e-mail ou telefone; `company_id` restringe à empresa. `user_id` do modelo
    é IGNORADO — ownership vem só da sessão.
    """
    del user_id  # nunca confiar no modelo (REQ-003)
    resolved = await _require_user_id()
    if isinstance(resolved, dict):
        return resolved
    contacts = await build_list_crm_contacts().execute(
        user_id=resolved,
        query=query,
        company_id=company_id,
    )
    return [_contact_dict(c) for c in contacts]


@tool
async def crm_upsert_contact(
    name: str,
    email: str | None = None,
    phone: str | None = None,
    contact_id: str | None = None,
    company_id: str | None = None,
    status: str | None = None,
    tags: list[str] | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """[CRM Jeff AI] `crm_upsert_contact` — cria ou atualiza contato no CRM nativo.

    Sem `contact_id` → cria. Com `contact_id` → atualiza. Exige `email` e/ou
    `phone`. NÃO usar MCP `contacts_*` / `lead_gen_*` no lugar desta tool.
    `user_id` do modelo é IGNORADO.
    """
    del user_id
    resolved = await _require_user_id()
    if isinstance(resolved, dict):
        return resolved
    try:
        if contact_id:
            contact = await build_update_crm_contact().execute(
                user_id=resolved,
                contact_id=contact_id,
                name=name,
                email=email,
                phone=phone,
                company_id=company_id,
                status=status,
                tags=tags,
            )
            if contact is None:
                return {"error": "Contact not found"}
        else:
            contact = await build_create_crm_contact().execute(
                user_id=resolved,
                name=name,
                email=email,
                phone=phone,
                company_id=company_id,
                status=status,
                tags=tags,
            )
    except DomainError as exc:
        return {"error": str(exc)}
    return _contact_dict(contact)


@tool
async def crm_add_note(
    body: str,
    contact_id: str | None = None,
    company_id: str | None = None,
    deal_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """[CRM Jeff AI] `crm_add_note` — nota imutável no CRM nativo (source=agent).

    Passe só um de `contact_id` / `company_id` / `deal_id`. Não confundir com
    MCP externo. `user_id` do modelo é IGNORADO.
    """
    del user_id
    resolved = await _require_user_id()
    if isinstance(resolved, dict):
        return resolved
    try:
        note = await build_create_crm_note().execute(
            user_id=resolved,
            body=body,
            source=NoteSource.AGENT,
            contact_id=contact_id,
            company_id=company_id,
            deal_id=deal_id,
        )
    except DomainError as exc:
        return {"error": str(exc)}
    return _note_dict(note)


@tool
async def crm_list_deals(
    stage: str | None = None,
    user_id: str | None = None,
) -> list[dict[str, Any]] | dict[str, Any]:
    """[CRM Jeff AI] `crm_list_deals` — lista deals do funil nativo.

    `stage` opcional: lead, qualified, proposal, won, lost. Este é o funil
    do módulo `/crm` — não existe equivalente em MCP `contacts_*`/`lead_gen_*`.
    `user_id` do modelo é IGNORADO.
    """
    del user_id
    resolved = await _require_user_id()
    if isinstance(resolved, dict):
        return resolved
    parsed: DealStage | None = None
    if stage is not None:
        try:
            parsed = DealStage(stage)
        except ValueError:
            return {"error": f"stage inválido: {stage!r}"}
    deals = await build_list_crm_deals().execute(user_id=resolved, stage=parsed)
    return [_deal_dict(d) for d in deals]


@tool
async def crm_create_deal(
    title: str,
    stage: str | None = None,
    value: str | None = None,
    currency: str | None = None,
    contact_id: str | None = None,
    company_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    r"""[CRM Jeff AI] `crm_create_deal` — cria deal no funil nativo (default lead).

    Use para LEADs no CRM Jeff AI (`/crm`). `value` string decimal (ex. "1500.00");
    moeda default BRL se value presente. Não usar MCP `lead_gen_*` no lugar.
    `user_id` do modelo é IGNORADO.
    """
    del user_id
    resolved = await _require_user_id()
    if isinstance(resolved, dict):
        return resolved
    parsed_stage: DealStage | None = None
    if stage is not None:
        try:
            parsed_stage = DealStage(stage)
        except ValueError:
            return {"error": f"stage inválido: {stage!r}"}
    parsed_value: Decimal | None = None
    if value is not None and value != "":
        try:
            parsed_value = Decimal(value)
        except (InvalidOperation, ValueError):
            return {"error": f"value inválido: {value!r}"}
    try:
        deal = await build_create_crm_deal().execute(
            user_id=resolved,
            title=title,
            stage=parsed_stage,
            value=parsed_value,
            currency=currency,
            contact_id=contact_id,
            company_id=company_id,
        )
    except DomainError as exc:
        return {"error": str(exc)}
    return _deal_dict(deal)


@tool
async def crm_move_deal(
    deal_id: str,
    stage: str,
    user_id: str | None = None,
) -> dict[str, Any]:
    """[CRM Jeff AI] `crm_move_deal` — move deal no funil nativo.

    Estágios: lead, qualified, proposal, won, lost. CRM Jeff AI apenas —
    não confundir com MCP. `user_id` do modelo é IGNORADO.
    """
    del user_id
    resolved = await _require_user_id()
    if isinstance(resolved, dict):
        return resolved
    try:
        deal = await build_move_crm_deal().execute(
            user_id=resolved, deal_id=deal_id, stage=stage
        )
    except DomainError as exc:
        return {"error": str(exc)}
    if deal is None:
        return {"error": "Deal not found"}
    return _deal_dict(deal)
