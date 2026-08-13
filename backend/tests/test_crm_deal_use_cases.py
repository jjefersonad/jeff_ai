"""Testes dos use cases de deals CRM (add-simple-crm-module-task-usecases-4).

Unit-1: create_deal defaults to lead
Unit-2: move_deal rejects invalid stage
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.application.ports.crm_repository import CrmRepositoryPort
from crm_repository_fakes import CrmRepositoryPortExtensions
from src.domain.crm import (
    Company,
    Contact,
    Deal,
    DealStage,
    Note,
    NoteSource,
    default_deal_stages,
)
from src.domain.shared.errors import DomainError


class _FakeCrmRepository(CrmRepositoryPortExtensions, CrmRepositoryPort):
    def __init__(self) -> None:
        self.companies: dict[str, Company] = {}
        self.contacts: dict[str, Contact] = {}
        self.deals: dict[str, Deal] = {}
        self.notes: list[Note] = []

    async def create_company(self, company: Company) -> Company:
        self.companies[company.id] = company
        return company

    async def get_company(self, user_id: str, company_id: str) -> Company | None:
        company = self.companies.get(company_id)
        if company is None or company.user_id != user_id:
            return None
        return company

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
        self.contacts[contact.id] = contact
        return contact

    async def get_contact(self, user_id: str, contact_id: str) -> Contact | None:
        contact = self.contacts.get(contact_id)
        if contact is None or contact.user_id != user_id:
            return None
        return contact

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
        self.deals[deal.id] = deal
        return deal

    async def get_deal(self, user_id: str, deal_id: str) -> Deal | None:
        deal = self.deals.get(deal_id)
        if deal is None or deal.user_id != user_id:
            return None
        return deal

    async def list_deals(
        self,
        user_id: str,
        *,
        stage: DealStage | None = None,
        include_archived: bool = False,
    ) -> list[Deal]:
        items = [d for d in self.deals.values() if d.user_id == user_id]
        if not include_archived:
            items = [d for d in items if d.archived_at is None]
        if stage is not None:
            items = [d for d in items if d.stage == stage]
        return items

    async def update_deal(self, deal: Deal) -> Deal | None:
        existing = self.deals.get(deal.id)
        if existing is None or existing.user_id != deal.user_id:
            return None
        self.deals[deal.id] = deal
        return deal

    async def archive_deal(self, user_id: str, deal_id: str) -> Deal | None:
        deal = await self.get_deal(user_id, deal_id)
        if deal is None:
            return None
        deal.archived_at = datetime.now(UTC)
        deal.updated_at = datetime.now(UTC)
        self.deals[deal.id] = deal
        return deal

    async def move_deal(
        self, user_id: str, deal_id: str, stage: DealStage
    ) -> Deal | None:
        deal = await self.get_deal(user_id, deal_id)
        if deal is None:
            return None
        deal.stage = stage
        deal.updated_at = datetime.now(UTC)
        self.deals[deal.id] = deal
        return deal

    async def create_note(self, note: Note) -> Note:
        self.notes.append(note)
        return note

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


async def test_create_deal_defaults_to_lead() -> None:
    """unit-1 (REQ-002): create sem stage → lead."""
    from src.application.use_cases.create_crm_deal import CreateCrmDeal

    repo = _FakeCrmRepository()
    deal = await CreateCrmDeal(repository=repo).execute(
        user_id="user-a", title="Proposta Acme"
    )
    assert deal.stage == DealStage.LEAD
    assert repo.deals[deal.id].stage == DealStage.LEAD


async def test_move_deal_rejects_invalid_stage() -> None:
    """unit-2 (REQ-003): stage inexistente → DomainError; stage original permanece."""
    from src.application.use_cases.create_crm_deal import CreateCrmDeal
    from src.application.use_cases.move_crm_deal import MoveCrmDeal

    repo = _FakeCrmRepository()
    deal = await CreateCrmDeal(repository=repo).execute(
        user_id="user-a", title="Deal", stage=DealStage.PROPOSAL
    )

    with pytest.raises(DomainError, match="stage"):
        await MoveCrmDeal(repository=repo).execute(
            user_id="user-a",
            deal_id=deal.id,
            stage="not-a-stage",
            source=NoteSource.USER,
        )

    stored = await repo.get_deal("user-a", deal.id)
    assert stored is not None
    assert stored.stage == DealStage.PROPOSAL


async def test_list_deal_stages_ordered() -> None:
    """REQ-001: list_stages retorna os estágios ordenados."""
    from src.application.use_cases.list_crm_deal_stages import ListCrmDealStages

    stages = await ListCrmDealStages().execute()
    assert stages == default_deal_stages()


async def test_create_deal_rejects_foreign_contact() -> None:
    """REQ-002: contact_id alienígena falha."""
    from src.application.use_cases.create_crm_contact import CreateCrmContact
    from src.application.use_cases.create_crm_deal import CreateCrmDeal

    repo = _FakeCrmRepository()
    contact = await CreateCrmContact(repository=repo).execute(
        user_id="user-b", name="Ana", email="a@x.com"
    )
    with pytest.raises(DomainError, match="contact_id"):
        await CreateCrmDeal(repository=repo).execute(
            user_id="user-a", title="Deal", contact_id=contact.id
        )


async def test_move_deal_to_won() -> None:
    """REQ-003: move para stage válido ok."""
    from src.application.use_cases.create_crm_deal import CreateCrmDeal
    from src.application.use_cases.move_crm_deal import MoveCrmDeal

    repo = _FakeCrmRepository()
    deal = await CreateCrmDeal(repository=repo).execute(
        user_id="user-a", title="Deal", stage=DealStage.PROPOSAL
    )
    moved = await MoveCrmDeal(repository=repo).execute(
        user_id="user-a", deal_id=deal.id, stage=DealStage.WON, source=NoteSource.USER
    )
    assert moved is not None
    assert moved.stage == DealStage.WON


async def test_move_deal_writes_note_with_transition_and_source() -> None:
    """unit-1/unit-2 (REQ-002/REQ-004): move grava crm_notes com 'de → para' e source."""
    from src.application.use_cases.create_crm_deal import CreateCrmDeal
    from src.application.use_cases.move_crm_deal import MoveCrmDeal

    repo = _FakeCrmRepository()
    deal = await CreateCrmDeal(repository=repo).execute(
        user_id="user-a", title="Deal", stage=DealStage.QUALIFIED
    )

    await MoveCrmDeal(repository=repo).execute(
        user_id="user-a",
        deal_id=deal.id,
        stage=DealStage.PROPOSAL,
        source=NoteSource.USER,
    )
    assert len(repo.notes) == 1
    assert repo.notes[0].deal_id == deal.id
    assert repo.notes[0].body == "qualified → proposal"
    assert repo.notes[0].source == NoteSource.USER

    await MoveCrmDeal(repository=repo).execute(
        user_id="user-a",
        deal_id=deal.id,
        stage=DealStage.NEGOTIATION,
        source=NoteSource.AGENT,
    )
    assert len(repo.notes) == 2
    assert repo.notes[1].body == "proposal → negotiation"
    assert repo.notes[1].source == NoteSource.AGENT


async def test_move_deal_invalid_stage_does_not_write_note() -> None:
    """Stage inválido -> DomainError antes de mover; nenhuma nota é criada."""
    from src.application.use_cases.create_crm_deal import CreateCrmDeal
    from src.application.use_cases.move_crm_deal import MoveCrmDeal

    repo = _FakeCrmRepository()
    deal = await CreateCrmDeal(repository=repo).execute(
        user_id="user-a", title="Deal", stage=DealStage.QUALIFIED
    )
    with pytest.raises(DomainError):
        await MoveCrmDeal(repository=repo).execute(
            user_id="user-a",
            deal_id=deal.id,
            stage="not-a-stage",
            source=NoteSource.USER,
        )
    assert repo.notes == []


async def test_list_deals_filter_and_archive() -> None:
    """REQ-004/005: filter por stage; archive oculta."""
    from src.application.use_cases.archive_crm_deal import ArchiveCrmDeal
    from src.application.use_cases.create_crm_deal import CreateCrmDeal
    from src.application.use_cases.list_crm_deals import ListCrmDeals

    repo = _FakeCrmRepository()
    await CreateCrmDeal(repository=repo).execute(
        user_id="user-a", title="A", stage=DealStage.QUALIFIED
    )
    proposal = await CreateCrmDeal(repository=repo).execute(
        user_id="user-a", title="B", stage=DealStage.PROPOSAL
    )
    filtered = await ListCrmDeals(repository=repo).execute(
        user_id="user-a", stage=DealStage.PROPOSAL
    )
    assert [d.id for d in filtered] == [proposal.id]

    await ArchiveCrmDeal(repository=repo).execute(
        user_id="user-a", deal_id=proposal.id
    )
    after = await ListCrmDeals(repository=repo).execute(user_id="user-a")
    assert all(d.id != proposal.id for d in after)


async def test_get_deal_cross_user_returns_none() -> None:
    """REQ-006: isolamento cross-user."""
    from src.application.use_cases.create_crm_deal import CreateCrmDeal
    from src.application.use_cases.get_crm_deal import GetCrmDeal

    repo = _FakeCrmRepository()
    deal = await CreateCrmDeal(repository=repo).execute(
        user_id="user-a", title="Deal"
    )
    assert (
        await GetCrmDeal(repository=repo).execute(
            user_id="user-b", deal_id=deal.id
        )
        is None
    )


async def test_update_deal_changes_title_and_value() -> None:
    """PATCH campos do deal sem contato."""
    from decimal import Decimal

    from src.application.use_cases.create_crm_deal import CreateCrmDeal
    from src.application.use_cases.update_crm_deal import UpdateCrmDeal

    repo = _FakeCrmRepository()
    deal = await CreateCrmDeal(repository=repo).execute(
        user_id="user-a", title="Acme"
    )
    updated = await UpdateCrmDeal(repository=repo).execute(
        user_id="user-a",
        deal_id=deal.id,
        title="Acme revisado",
        value=Decimal("1500.00"),
        set_value=True,
        currency="BRL",
    )
    assert updated is not None
    assert updated.title == "Acme revisado"
    assert updated.value == Decimal("1500.00")
    assert updated.currency == "BRL"


async def test_update_deal_stage_writes_transition_note() -> None:
    """Mudança de estágio no update grava a mesma nota de MoveCrmDeal."""
    from src.application.use_cases.create_crm_deal import CreateCrmDeal
    from src.application.use_cases.update_crm_deal import UpdateCrmDeal

    repo = _FakeCrmRepository()
    deal = await CreateCrmDeal(repository=repo).execute(
        user_id="user-a", title="Acme"
    )
    updated = await UpdateCrmDeal(repository=repo).execute(
        user_id="user-a",
        deal_id=deal.id,
        stage=DealStage.QUALIFIED,
    )
    assert updated is not None
    assert updated.stage == DealStage.QUALIFIED
    assert len(repo.notes) == 1
    assert repo.notes[0].body == "lead → qualified"
