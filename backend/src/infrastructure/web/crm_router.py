"""Rotas REST do CRM (`/api/crm/contacts|companies|notes|deals`).

`user_id` vem só de `require_auth` — nunca do body. DomainError → 422;
miss / cross-user → 404. Notas não têm PATCH (imutáveis na v1).
"""
from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.application.ports.crm_repository import CrmRepositoryPort
from src.application.use_cases.archive_crm_company import ArchiveCrmCompany
from src.application.use_cases.archive_crm_contact import ArchiveCrmContact
from src.application.use_cases.archive_crm_deal import ArchiveCrmDeal
from src.application.use_cases.create_crm_company import CreateCrmCompany
from src.application.use_cases.create_crm_contact import CreateCrmContact
from src.application.use_cases.create_crm_deal import CreateCrmDeal
from src.application.use_cases.create_crm_note import CreateCrmNote
from src.application.use_cases.get_crm_company import GetCrmCompany
from src.application.use_cases.get_crm_contact import GetCrmContact
from src.application.use_cases.get_crm_deal import GetCrmDeal
from src.application.use_cases.list_crm_companies import ListCrmCompanies
from src.application.use_cases.list_crm_contacts import ListCrmContacts
from src.application.use_cases.list_crm_deal_stages import ListCrmDealStages
from src.application.use_cases.list_crm_deals import ListCrmDeals
from src.application.use_cases.list_crm_notes import ListCrmNotes
from src.application.use_cases.move_crm_deal import MoveCrmDeal
from src.application.use_cases.update_crm_company import UpdateCrmCompany
from src.application.use_cases.update_crm_contact import UpdateCrmContact
from src.domain.crm import Company, Contact, Deal, DealStage, Note, NoteSource
from src.domain.shared.errors import DomainError
from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.users import User
from src.infrastructure.persistence.crm_repository import PostgresCrmRepository

router = APIRouter()


def _crm_repository() -> CrmRepositoryPort:
    """Constrói o repositório a partir de `POSTGRES_URI`."""
    return PostgresCrmRepository(os.environ["POSTGRES_URI"])


class ContactCreateRequest(BaseModel):
    """Corpo de `POST /api/crm/contacts`. Sem ownership."""

    name: str
    email: str | None = None
    phone: str | None = None
    company_id: str | None = None
    status: str | None = None
    tags: list[str] | None = None


class ContactUpdateRequest(BaseModel):
    """Corpo de `PATCH /api/crm/contacts/{id}`."""

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    company_id: str | None = None
    clear_company: bool = False
    status: str | None = None
    tags: list[str] | None = None


class ContactResponse(BaseModel):
    """Contrato HTTP de contato."""

    id: str
    user_id: str
    name: str
    email: str | None
    phone: str | None
    company_id: str | None
    status: str | None
    tags: list[str]
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CompanyCreateRequest(BaseModel):
    """Corpo de `POST /api/crm/companies`."""

    name: str
    website: str | None = None
    domain: str | None = None
    phone: str | None = None
    notes: str | None = None


class CompanyUpdateRequest(BaseModel):
    """Corpo de `PATCH /api/crm/companies/{id}`."""

    name: str | None = None
    website: str | None = None
    domain: str | None = None
    phone: str | None = None
    notes: str | None = None


class CompanyResponse(BaseModel):
    """Contrato HTTP de empresa."""

    id: str
    user_id: str
    name: str
    website: str | None
    domain: str | None
    phone: str | None
    notes: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


def _contact_response(contact: Contact) -> ContactResponse:
    return ContactResponse(
        id=contact.id,
        user_id=contact.user_id,
        name=contact.name,
        email=contact.email,
        phone=contact.phone,
        company_id=contact.company_id,
        status=contact.status,
        tags=list(contact.tags),
        archived_at=contact.archived_at,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
    )


def _company_response(company: Company) -> CompanyResponse:
    return CompanyResponse(
        id=company.id,
        user_id=company.user_id,
        name=company.name,
        website=company.website,
        domain=company.domain,
        phone=company.phone,
        notes=company.notes,
        archived_at=company.archived_at,
        created_at=company.created_at,
        updated_at=company.updated_at,
    )


def _require_user(user: User | None) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


# --- Contacts ----------------------------------------------------------------


@router.post("/api/crm/contacts", status_code=201)
async def create_contact_endpoint(
    body: ContactCreateRequest,
    user: User | None = Depends(require_auth),
    repository: CrmRepositoryPort = Depends(_crm_repository),
) -> ContactResponse:
    """Cria contato do usuário autenticado."""
    actor = _require_user(user)
    try:
        contact = await CreateCrmContact(repository=repository).execute(
            user_id=actor.id,
            name=body.name,
            email=body.email,
            phone=body.phone,
            company_id=body.company_id,
            status=body.status,
            tags=body.tags,
        )
    except DomainError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _contact_response(contact)


@router.get("/api/crm/contacts")
async def list_contacts_endpoint(
    query: str | None = Query(default=None),
    company_id: str | None = Query(default=None),
    archived: bool = Query(default=False),
    user: User | None = Depends(require_auth),
    repository: CrmRepositoryPort = Depends(_crm_repository),
) -> list[ContactResponse]:
    """Lista contatos do usuário."""
    actor = _require_user(user)
    contacts = await ListCrmContacts(repository=repository).execute(
        user_id=actor.id,
        query=query,
        company_id=company_id,
        include_archived=archived,
    )
    return [_contact_response(c) for c in contacts]


@router.get("/api/crm/contacts/{contact_id}")
async def get_contact_endpoint(
    contact_id: str,
    user: User | None = Depends(require_auth),
    repository: CrmRepositoryPort = Depends(_crm_repository),
) -> ContactResponse:
    """Obtém contato próprio; miss → 404."""
    actor = _require_user(user)
    contact = await GetCrmContact(repository=repository).execute(
        user_id=actor.id, contact_id=contact_id
    )
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return _contact_response(contact)


@router.patch("/api/crm/contacts/{contact_id}")
async def update_contact_endpoint(
    contact_id: str,
    body: ContactUpdateRequest,
    user: User | None = Depends(require_auth),
    repository: CrmRepositoryPort = Depends(_crm_repository),
) -> ContactResponse:
    """Atualiza contato próprio."""
    actor = _require_user(user)
    try:
        contact = await UpdateCrmContact(repository=repository).execute(
            user_id=actor.id,
            contact_id=contact_id,
            name=body.name,
            email=body.email,
            phone=body.phone,
            company_id=body.company_id,
            clear_company=body.clear_company,
            status=body.status,
            tags=body.tags,
        )
    except DomainError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return _contact_response(contact)


@router.post("/api/crm/contacts/{contact_id}/archive")
async def archive_contact_endpoint(
    contact_id: str,
    user: User | None = Depends(require_auth),
    repository: CrmRepositoryPort = Depends(_crm_repository),
) -> ContactResponse:
    """Arquiva contato próprio."""
    actor = _require_user(user)
    contact = await ArchiveCrmContact(repository=repository).execute(
        user_id=actor.id, contact_id=contact_id
    )
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return _contact_response(contact)


# --- Companies ---------------------------------------------------------------


@router.post("/api/crm/companies", status_code=201)
async def create_company_endpoint(
    body: CompanyCreateRequest,
    user: User | None = Depends(require_auth),
    repository: CrmRepositoryPort = Depends(_crm_repository),
) -> CompanyResponse:
    """Cria empresa do usuário autenticado."""
    actor = _require_user(user)
    try:
        company = await CreateCrmCompany(repository=repository).execute(
            user_id=actor.id,
            name=body.name,
            website=body.website,
            domain=body.domain,
            phone=body.phone,
            notes=body.notes,
        )
    except DomainError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _company_response(company)


@router.get("/api/crm/companies")
async def list_companies_endpoint(
    query: str | None = Query(default=None),
    archived: bool = Query(default=False),
    user: User | None = Depends(require_auth),
    repository: CrmRepositoryPort = Depends(_crm_repository),
) -> list[CompanyResponse]:
    """Lista empresas do usuário."""
    actor = _require_user(user)
    companies = await ListCrmCompanies(repository=repository).execute(
        user_id=actor.id,
        query=query,
        include_archived=archived,
    )
    return [_company_response(c) for c in companies]


@router.get("/api/crm/companies/{company_id}")
async def get_company_endpoint(
    company_id: str,
    user: User | None = Depends(require_auth),
    repository: CrmRepositoryPort = Depends(_crm_repository),
) -> CompanyResponse:
    """Obtém empresa própria; miss → 404."""
    actor = _require_user(user)
    company = await GetCrmCompany(repository=repository).execute(
        user_id=actor.id, company_id=company_id
    )
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return _company_response(company)


@router.patch("/api/crm/companies/{company_id}")
async def update_company_endpoint(
    company_id: str,
    body: CompanyUpdateRequest,
    user: User | None = Depends(require_auth),
    repository: CrmRepositoryPort = Depends(_crm_repository),
) -> CompanyResponse:
    """Atualiza empresa própria."""
    actor = _require_user(user)
    try:
        company = await UpdateCrmCompany(repository=repository).execute(
            user_id=actor.id,
            company_id=company_id,
            name=body.name,
            website=body.website,
            domain=body.domain,
            phone=body.phone,
            notes=body.notes,
        )
    except DomainError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return _company_response(company)


@router.post("/api/crm/companies/{company_id}/archive")
async def archive_company_endpoint(
    company_id: str,
    user: User | None = Depends(require_auth),
    repository: CrmRepositoryPort = Depends(_crm_repository),
) -> CompanyResponse:
    """Arquiva empresa própria."""
    actor = _require_user(user)
    company = await ArchiveCrmCompany(repository=repository).execute(
        user_id=actor.id, company_id=company_id
    )
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return _company_response(company)


# --- Notes -------------------------------------------------------------------


class NoteCreateRequest(BaseModel):
    """Corpo de `POST /api/crm/notes`. Exatamente um alvo."""

    body: str
    source: str = "user"
    contact_id: str | None = None
    company_id: str | None = None
    deal_id: str | None = None


class NoteResponse(BaseModel):
    """Contrato HTTP de nota."""

    id: str
    user_id: str
    body: str
    source: str
    contact_id: str | None
    company_id: str | None
    deal_id: str | None
    created_at: datetime


def _note_response(note: Note) -> NoteResponse:
    return NoteResponse(
        id=note.id,
        user_id=note.user_id,
        body=note.body,
        source=note.source.value,
        contact_id=note.contact_id,
        company_id=note.company_id,
        deal_id=note.deal_id,
        created_at=note.created_at,
    )


@router.post("/api/crm/notes", status_code=201)
async def create_note_endpoint(
    body: NoteCreateRequest,
    user: User | None = Depends(require_auth),
    repository: CrmRepositoryPort = Depends(_crm_repository),
) -> NoteResponse:
    """Cria nota imutável ligada a um alvo."""
    actor = _require_user(user)
    try:
        source = NoteSource(body.source)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"source inválido: {body.source}") from exc
    try:
        note = await CreateCrmNote(repository=repository).execute(
            user_id=actor.id,
            body=body.body,
            source=source,
            contact_id=body.contact_id,
            company_id=body.company_id,
            deal_id=body.deal_id,
        )
    except DomainError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _note_response(note)


@router.get("/api/crm/notes")
async def list_notes_endpoint(
    contact_id: str | None = Query(default=None),
    company_id: str | None = Query(default=None),
    deal_id: str | None = Query(default=None),
    user: User | None = Depends(require_auth),
    repository: CrmRepositoryPort = Depends(_crm_repository),
) -> list[NoteResponse]:
    """Lista notas de exatamente um alvo."""
    actor = _require_user(user)
    try:
        notes = await ListCrmNotes(repository=repository).execute(
            user_id=actor.id,
            contact_id=contact_id,
            company_id=company_id,
            deal_id=deal_id,
        )
    except DomainError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [_note_response(n) for n in notes]


# --- Deals -------------------------------------------------------------------


class DealCreateRequest(BaseModel):
    """Corpo de `POST /api/crm/deals`."""

    title: str
    stage: str | None = None
    value: Decimal | None = None
    currency: str | None = None
    contact_id: str | None = None
    company_id: str | None = None


class DealMoveRequest(BaseModel):
    """Corpo de `POST /api/crm/deals/{id}/move`."""

    stage: str


class DealResponse(BaseModel):
    """Contrato HTTP de deal."""

    id: str
    user_id: str
    title: str
    stage: str
    value: Decimal | None
    currency: str | None
    contact_id: str | None
    company_id: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


def _deal_response(deal: Deal) -> DealResponse:
    return DealResponse(
        id=deal.id,
        user_id=deal.user_id,
        title=deal.title,
        stage=deal.stage.value,
        value=deal.value,
        currency=deal.currency,
        contact_id=deal.contact_id,
        company_id=deal.company_id,
        archived_at=deal.archived_at,
        created_at=deal.created_at,
        updated_at=deal.updated_at,
    )


@router.get("/api/crm/deals/stages")
async def list_deal_stages_endpoint(
    user: User | None = Depends(require_auth),
) -> list[str]:
    """Lista estágios fixos do funil."""
    _require_user(user)
    stages = await ListCrmDealStages().execute()
    return [s.value for s in stages]


@router.post("/api/crm/deals", status_code=201)
async def create_deal_endpoint(
    body: DealCreateRequest,
    user: User | None = Depends(require_auth),
    repository: CrmRepositoryPort = Depends(_crm_repository),
) -> DealResponse:
    """Cria deal (stage default lead)."""
    actor = _require_user(user)
    stage: DealStage | None = None
    if body.stage is not None:
        try:
            stage = DealStage(body.stage)
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail=f"stage inválido: {body.stage}"
            ) from exc
    try:
        deal = await CreateCrmDeal(repository=repository).execute(
            user_id=actor.id,
            title=body.title,
            stage=stage,
            value=body.value,
            currency=body.currency,
            contact_id=body.contact_id,
            company_id=body.company_id,
        )
    except DomainError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _deal_response(deal)


@router.get("/api/crm/deals")
async def list_deals_endpoint(
    stage: str | None = Query(default=None),
    archived: bool = Query(default=False),
    user: User | None = Depends(require_auth),
    repository: CrmRepositoryPort = Depends(_crm_repository),
) -> list[DealResponse]:
    """Lista deals do usuário; filtro opcional por stage."""
    actor = _require_user(user)
    stage_filter: DealStage | None = None
    if stage is not None:
        try:
            stage_filter = DealStage(stage)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"stage inválido: {stage}") from exc
    deals = await ListCrmDeals(repository=repository).execute(
        user_id=actor.id,
        stage=stage_filter,
        include_archived=archived,
    )
    return [_deal_response(d) for d in deals]


@router.get("/api/crm/deals/{deal_id}")
async def get_deal_endpoint(
    deal_id: str,
    user: User | None = Depends(require_auth),
    repository: CrmRepositoryPort = Depends(_crm_repository),
) -> DealResponse:
    """Obtém deal próprio; miss → 404."""
    actor = _require_user(user)
    deal = await GetCrmDeal(repository=repository).execute(
        user_id=actor.id, deal_id=deal_id
    )
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return _deal_response(deal)


@router.post("/api/crm/deals/{deal_id}/move")
async def move_deal_endpoint(
    deal_id: str,
    body: DealMoveRequest,
    user: User | None = Depends(require_auth),
    repository: CrmRepositoryPort = Depends(_crm_repository),
) -> DealResponse:
    """Move deal para outro estágio."""
    actor = _require_user(user)
    try:
        deal = await MoveCrmDeal(repository=repository).execute(
            user_id=actor.id, deal_id=deal_id, stage=body.stage
        )
    except DomainError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return _deal_response(deal)


@router.post("/api/crm/deals/{deal_id}/archive")
async def archive_deal_endpoint(
    deal_id: str,
    user: User | None = Depends(require_auth),
    repository: CrmRepositoryPort = Depends(_crm_repository),
) -> DealResponse:
    """Arquiva deal próprio."""
    actor = _require_user(user)
    deal = await ArchiveCrmDeal(repository=repository).execute(
        user_id=actor.id, deal_id=deal_id
    )
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return _deal_response(deal)
