"""Port de repositório CRM (contacts, companies, deals, notes).

Abstrai a persistência Postgres do restante da camada de aplicação.
Todas as leituras/escritas são escopadas a `user_id` — miss cross-user
retorna `None` / lista vazia, nunca vaza existência.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.crm import Company, Contact, Deal, DealStage, Note


class CrmRepositoryPort(ABC):
    """Persistência CRM escopada por usuário."""

    # --- Companies -----------------------------------------------------------

    @abstractmethod
    async def create_company(self, company: Company) -> Company:
        """Cria uma nova empresa e devolve a entidade (com id se gerado)."""
        raise NotImplementedError

    @abstractmethod
    async def get_company(self, user_id: str, company_id: str) -> Company | None:
        """Retorna a empresa do user ou ``None`` (inclui miss cross-user)."""
        raise NotImplementedError

    @abstractmethod
    async def list_companies(
        self,
        user_id: str,
        *,
        query: str | None = None,
        include_archived: bool = False,
    ) -> list[Company]:
        """Lista empresas do user; busca opcional por nome/domínio."""
        raise NotImplementedError

    @abstractmethod
    async def update_company(self, company: Company) -> Company | None:
        """Atualiza empresa própria; None se não existir para o user_id."""
        raise NotImplementedError

    @abstractmethod
    async def archive_company(self, user_id: str, company_id: str) -> Company | None:
        """Arquiva (soft-delete); ``None`` se miss."""
        raise NotImplementedError

    # --- Contacts ------------------------------------------------------------

    @abstractmethod
    async def create_contact(self, contact: Contact) -> Contact:
        """Cria um novo contato."""
        raise NotImplementedError

    @abstractmethod
    async def get_contact(self, user_id: str, contact_id: str) -> Contact | None:
        """Retorna o contato do user ou None."""
        raise NotImplementedError

    @abstractmethod
    async def list_contacts(
        self,
        user_id: str,
        *,
        query: str | None = None,
        company_id: str | None = None,
        include_archived: bool = False,
    ) -> list[Contact]:
        """Lista contatos do user; filtro opcional por termo/empresa."""
        raise NotImplementedError

    @abstractmethod
    async def update_contact(self, contact: Contact) -> Contact | None:
        """Atualiza contato próprio; None se miss."""
        raise NotImplementedError

    @abstractmethod
    async def archive_contact(self, user_id: str, contact_id: str) -> Contact | None:
        """Arquiva (soft-delete); ``None`` se miss."""
        raise NotImplementedError

    # --- Deals ---------------------------------------------------------------

    @abstractmethod
    async def create_deal(self, deal: Deal) -> Deal:
        """Cria um novo deal."""
        raise NotImplementedError

    @abstractmethod
    async def get_deal(self, user_id: str, deal_id: str) -> Deal | None:
        """Retorna o deal do user ou None."""
        raise NotImplementedError

    @abstractmethod
    async def list_deals(
        self,
        user_id: str,
        *,
        stage: DealStage | None = None,
        include_archived: bool = False,
    ) -> list[Deal]:
        """Lista deals do user; filtro opcional por estágio."""
        raise NotImplementedError

    @abstractmethod
    async def update_deal(self, deal: Deal) -> Deal | None:
        """Atualiza deal próprio; None se miss."""
        raise NotImplementedError

    @abstractmethod
    async def archive_deal(self, user_id: str, deal_id: str) -> Deal | None:
        """Arquiva (soft-delete); ``None`` se miss."""
        raise NotImplementedError

    @abstractmethod
    async def move_deal(
        self, user_id: str, deal_id: str, stage: DealStage
    ) -> Deal | None:
        """Atualiza só o estágio do deal; None se miss."""
        raise NotImplementedError

    # --- Notes ---------------------------------------------------------------

    @abstractmethod
    async def create_note(self, note: Note) -> Note:
        """Cria uma nota imutável."""
        raise NotImplementedError

    @abstractmethod
    async def list_notes_for_contact(
        self, user_id: str, contact_id: str
    ) -> list[Note]:
        """Notas do contato, mais recente primeiro."""
        raise NotImplementedError

    @abstractmethod
    async def list_notes_for_company(
        self, user_id: str, company_id: str
    ) -> list[Note]:
        """Notas da empresa, mais recente primeiro."""
        raise NotImplementedError

    @abstractmethod
    async def list_notes_for_deal(self, user_id: str, deal_id: str) -> list[Note]:
        """Notas do deal, mais recente primeiro."""
        raise NotImplementedError
