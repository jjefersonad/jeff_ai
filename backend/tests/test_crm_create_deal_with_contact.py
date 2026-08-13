"""CreateCrmDeal orchestrates optional contact (backend-create-1)."""
from __future__ import annotations

import pytest

from src.application.use_cases.create_crm_contact import CreateCrmContact
from src.application.use_cases.create_crm_deal import CreateCrmDeal
from src.domain.crm import Contact, DealStage
from src.domain.shared.errors import DomainError
from test_crm_deal_use_cases import _FakeCrmRepository as _BaseFake


class _FakeCrmRepository(_BaseFake):
    async def update_contact(self, contact: Contact) -> Contact | None:
        existing = self.contacts.get(contact.id)
        if existing is None or existing.user_id != contact.user_id:
            return None
        self.contacts[contact.id] = contact
        return contact

    async def get_contact_by_email(
        self, user_id: str, email: str
    ) -> Contact | None:
        needle = email.strip().lower()
        for contact in self.contacts.values():
            if (
                contact.user_id == user_id
                and contact.email
                and contact.email.lower() == needle
            ):
                return contact
        return None


async def test_create_deal_title_only_has_no_contact() -> None:
    """unit-1: only title → lead deal, contact_id=None, no contact created."""
    repo = _FakeCrmRepository()
    deal = await CreateCrmDeal(repository=repo).execute(
        user_id="user-a", title="Acme"
    )
    assert deal.stage == DealStage.LEAD
    assert deal.contact_id is None
    assert repo.contacts == {}
    assert not hasattr(deal, "source_lead_id")


async def test_create_deal_without_contact_id_creates_contact_from_email() -> None:
    """unit-2: no contact_id + email → Contact created and Deal.contact_id points to it."""
    repo = _FakeCrmRepository()
    deal = await CreateCrmDeal(repository=repo).execute(
        user_id="user-a",
        title="Acme",
        email="joao@acme.com",
    )
    assert deal.contact_id is not None
    contact = repo.contacts[deal.contact_id]
    assert contact.email == "joao@acme.com"
    assert len(repo.contacts) == 1


async def test_create_deal_with_contact_id_updates_and_does_not_duplicate() -> None:
    """unit-3: existing contact_id + new phone → update, link, no duplicate."""
    repo = _FakeCrmRepository()
    existing = await CreateCrmContact(repository=repo).execute(
        user_id="user-a", name="João", email="joao@acme.com"
    )
    deal = await CreateCrmDeal(repository=repo).execute(
        user_id="user-a",
        title="Acme",
        contact_id=existing.id,
        phone="11999998888",
    )
    assert deal.contact_id == existing.id
    assert len(repo.contacts) == 1
    assert repo.contacts[existing.id].phone == "11999998888"


async def test_create_deal_empty_contact_name_falls_back_to_title() -> None:
    """unit-4: empty contact name + email → Contact.name is the deal title."""
    repo = _FakeCrmRepository()
    deal = await CreateCrmDeal(repository=repo).execute(
        user_id="user-a",
        title="Acme",
        contact_name="",
        email="joao@acme.com",
    )
    contact = repo.contacts[deal.contact_id]  # type: ignore[index]
    assert contact.name == "Acme"


async def test_create_deal_contact_without_identifier_persists_nothing() -> None:
    """unit-5: name without email/phone → DomainError; no deal, no contact."""
    repo = _FakeCrmRepository()
    with pytest.raises(DomainError, match="email ou phone"):
        await CreateCrmDeal(repository=repo).execute(
            user_id="user-a",
            title="Acme",
            contact_name="João",
        )
    assert repo.deals == {}
    assert repo.contacts == {}


async def test_create_deal_reuses_contact_matched_by_email() -> None:
    """unit-6: no contact_id + email already in repo → update, no duplicate."""
    repo = _FakeCrmRepository()
    existing = await CreateCrmContact(repository=repo).execute(
        user_id="user-a", name="João", email="joao@acme.com"
    )
    deal = await CreateCrmDeal(repository=repo).execute(
        user_id="user-a",
        title="Acme",
        email="joao@acme.com",
        phone="11999998888",
    )
    assert deal.contact_id == existing.id
    assert len(repo.contacts) == 1
    assert repo.contacts[existing.id].phone == "11999998888"


async def test_create_deal_phone_only_creates_contact_and_deal() -> None:
    """unit-7: name + only phone → contact and deal created and linked."""
    repo = _FakeCrmRepository()
    deal = await CreateCrmDeal(repository=repo).execute(
        user_id="user-a",
        title="Acme",
        contact_name="João",
        phone="11999998888",
    )
    assert deal.contact_id is not None
    contact = repo.contacts[deal.contact_id]
    assert contact.name == "João"
    assert contact.phone == "11999998888"
    assert contact.email is None
    assert len(repo.deals) == 1


async def test_update_deal_nested_email_creates_contact() -> None:
    """Update com e-mail cria contato e vincula ao deal existente."""
    from src.application.use_cases.update_crm_deal import UpdateCrmDeal

    repo = _FakeCrmRepository()
    deal = await CreateCrmDeal(repository=repo).execute(
        user_id="user-a", title="Acme"
    )
    updated = await UpdateCrmDeal(repository=repo).execute(
        user_id="user-a",
        deal_id=deal.id,
        title="Acme",
        contact_name="Ana",
        email="ana@x.com",
        apply_contact=True,
    )
    assert updated is not None
    assert updated.contact_id is not None
    contact = repo.contacts[updated.contact_id]
    assert contact.name == "Ana"
    assert contact.email == "ana@x.com"
