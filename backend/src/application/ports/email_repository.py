"""Port de repositório de emails.

Abstrai a persistência de `Email` (Postgres no adapter) do restante
da camada de aplicação. Toda operação é filtrada por `user_id` via
subquery em `email_accounts` — miss cross-user retorna `None` ou `False`,
nunca exceção, para não revelar se a entrada existe.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.email import Email, ParsedAttachment, ParsedMessage


class EmailRepositoryPort(ABC):
    """Persiste `Email`, sempre escopado ao `user_id` dono da conta."""

    @abstractmethod
    async def upsert_email(
        self,
        email_account_id: str,
        message: ParsedMessage,
        attachments: list[ParsedAttachment] | None = None,
        contact_id: str | None = None,
    ) -> Email:
        """Insere/atualiza `message`, idempotente por `email_account_id`+`message_id`.

        Substitui os `email_attachments` existentes da mensagem pelos
        fornecidos em `attachments` (lista vazia/`None` limpa os anexos).
        `contact_id` opcionalmente associa o email a um `Contact` do CRM
        (REQ-006 `email-inbox`). Quando uma linha já existe e um novo
        `contact_id=None` é passado, o link anterior é preservado — uma
        re-sincronização não deve desassociar mensagens já linkadas.
        """
        raise NotImplementedError

    @abstractmethod
    async def list_by_account(
        self,
        user_id: str,
        account_id: str | None = None,
        folder: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Email]:
        """Retorna emails do user, ordenados por `received_at` DESC.

        Sem `account_id`/`folder`, retorna o inbox unificado de todas as
        contas do user. Cruzar `user_id` (outro user) sempre retorna lista
        vazia — miss cross-user nunca é exceção.
        """
        raise NotImplementedError

    @abstractmethod
    async def get(self, user_id: str, email_id: str) -> Email | None:
        """Retorna o email do `user_id` ou `None` (miss ou cross-user)."""
        raise NotImplementedError

    @abstractmethod
    async def get_by_message_id(
        self, user_id: str, message_id: str
    ) -> Email | None:
        """Retorna o email do `user_id` cujo `message_id` (header IMAP) bate, ou `None`.

        O `message_id` é o header `Message-ID:` RFC822 — não o `id` UUID da
        linha. Necessário para o caso de uso de reply (REQ-005 email-inbox):
        o frontend envia o `Message-ID` original como `in_reply_to` no
        payload do `POST /api/email/send` e o backend precisa resolver para
        a linha persistida para propagar `thread_id` + prefixar o subject.
        Cruzar `user_id` (outro user) retorna `None` para não revelar se a
        mensagem existe em outra conta.
        """
        raise NotImplementedError

    @abstractmethod
    async def search(
        self,
        user_id: str,
        account_id: str | None,
        query: str,
        limit: int,
    ) -> list[Email]:
        """Busca por `query` em `subject`, `body_text` e `from_address` (ILIKE %query%)."""
        raise NotImplementedError

    @abstractmethod
    async def mark_read(self, user_id: str, email_id: str) -> bool:
        """Marca email como lido; `True` se atualizado, `False` se miss/cross-user."""
        raise NotImplementedError

    @abstractmethod
    async def move_folder(self, user_id: str, email_id: str, folder: str) -> bool:
        """Move email para outra folder; `True` se movido, `False` se miss/cross-user."""
        raise NotImplementedError
