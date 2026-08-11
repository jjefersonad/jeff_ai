"""SendEmail use case — envio de email via SMTP da conta configurada."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from src.application.integrations.config_schemas import (
    ImapIntegrationConfig,
    validate_config,
)
from src.application.ports.email_account_repository import (
    EmailAccountRepositoryPort,
)
from src.application.ports.email_repository import EmailRepositoryPort
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.domain.email import ParsedMessage
from src.infrastructure.email.smtp_client import send_email_via_smtp

_SENT_FOLDER = "Sent"

_INTEGRATION_TYPE = "imap"
_RE_PREFIX = "Re: "


def _prefixed_subject(subject: str) -> str:
    """Adiciona o prefixo `Re: ` se o subject ainda não o tem."""
    if subject.startswith(_RE_PREFIX):
        return subject
    return _RE_PREFIX + subject


@dataclass(frozen=True)
class SendEmailResult:
    """Resultado do envio de email."""

    message_id: str
    sent_at: datetime
    thread_id: str | None = None


class SendEmail:
    """Envia email via SMTP usando as credenciais da conta IMAP do usuário."""

    def __init__(
        self,
        *,
        email_account_repository: EmailAccountRepositoryPort,
        integration_repository: UserIntegrationRepositoryPort,
        email_repository: EmailRepositoryPort,
    ) -> None:
        """Recebe as portas de repositório por injeção.

        `email_repository` é usado para resolver o email original em replies
        (o caller passa `in_reply_to=<email_id>`, e o use case propaga
        `thread_id` e prefixa o `subject` com `Re:` quando ainda não estiver
        prefixado — REQ-005 email-inbox) e para persistir a mensagem enviada
        na pasta `Sent`, sem o que ela nunca apareceria em `list_emails`.
        """
        self._email_account_repository = email_account_repository
        self._integration_repository = integration_repository
        self._email_repository = email_repository

    async def execute(
        self,
        *,
        user_id: str,
        account_id: str,
        to_addresses: list[str],
        subject: str,
        body_text: str,
        body_html: str | None = None,
        cc_addresses: list[str] | None = None,
        bcc_addresses: list[str] | None = None,
        in_reply_to: str | None = None,
        references: str | None = None,
        attachments: list[tuple[str, bytes, str]] | None = None,
    ) -> SendEmailResult:
        """Envia email via SMTP usando as credenciais da conta.

        Args:
            in_reply_to: ID de um email do próprio `user_id` ao qual esta
                mensagem é reply. Quando informado, o use case propaga o
                `thread_id` desse email e prefixa o `subject` com `Re: `
                (idempotente — não duplica se já prefixado). O cabeçalho
                SMTP `In-Reply-To` é definido a partir do `message_id` do
                email original.

        Raises:
            ValueError: conta não encontrada, não pertence ao usuário,
                ou `in_reply_to` referencia email de outro user/inexistente.
            SmtpAuthError: autenticação SMTP recusada.
            Exception: falhas de rede/timeout propagam sem embrulho.
        """
        account = await self._email_account_repository.get(user_id, account_id)
        if account is None:
            raise ValueError("Email account not found")

        integration = await self._integration_repository.get(account.user_integration_id)
        if integration is None:
            raise ValueError("Email account integration credentials not found")

        config_dict = integration.config
        config = validate_config(_INTEGRATION_TYPE, config_dict)
        assert isinstance(config, ImapIntegrationConfig)

        thread_id: str | None = None
        smtp_in_reply_to: str | None = None
        smtp_references: str | None = references
        final_subject = subject

        if in_reply_to is not None:
            # `in_reply_to` é o header IMAP `Message-ID:` da mensagem
            # original (enviado pelo frontend como `email.message_id`),
            # NÃO o UUID da linha. Resolver por `message_id` via
            # `get_by_message_id` em vez de `get(user_id, email_id)` —
            # este último tentava casar o Message-ID (string IMAP) contra a
            # coluna `id` (UUID) e levantava
            # `psycopg.errors.InvalidTextRepresentation` (bug em produção
            # 2026-08-10).
            original = await self._email_repository.get_by_message_id(
                user_id, in_reply_to
            )
            if original is None:
                raise ValueError("Reply target email not found")
            thread_id = original.thread_id
            final_subject = _prefixed_subject(subject or original.subject or "")
            smtp_in_reply_to = original.message_id
            if references is None and original.message_id:
                smtp_references = original.message_id

        message_id = await send_email_via_smtp(
            config=config,
            from_name=account.display_name,
            to_addresses=to_addresses,
            cc_addresses=cc_addresses or [],
            bcc_addresses=bcc_addresses or [],
            subject=final_subject,
            body_text=body_text,
            body_html=body_html,
            in_reply_to=smtp_in_reply_to,
            references=smtp_references,
            attachments=attachments,
        )
        sent_at = datetime.now(UTC)

        # Persist the dispatched message so it appears in the account's Sent
        # folder — without this, `send_email` reports success but the email
        # is invisible to `list_emails`/`GET /api/email?folder=Sent` until
        # (if ever) the provider round-trips it back via IMAP sync.
        sender_address = config.smtp_username or config.imap_username
        sent_message = ParsedMessage(
            uid=message_id,
            message_id=message_id,
            folder=_SENT_FOLDER,
            from_address=sender_address,
            from_name=account.display_name,
            to_addresses=to_addresses,
            subject=final_subject,
            body_html=body_html,
            body_text=body_text,
            received_at=sent_at,
        )
        saved = await self._email_repository.upsert_email(account.id, sent_message)
        await self._email_repository.mark_read(user_id, saved.id)

        return SendEmailResult(
            message_id=message_id,
            sent_at=sent_at,
            thread_id=thread_id,
        )
