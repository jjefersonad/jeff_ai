"""SendEmail use case — envio de email via SMTP da conta configurada."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from src.application.integrations.config_schemas import (
    GmailIntegrationConfig,
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
from src.domain.integrations import UserIntegration
from src.infrastructure.email.gmail_oauth import (
    ensure_fresh_token as _real_ensure_fresh_token,
)
from src.infrastructure.email.smtp_client import resolve_bodies, send_email_via_smtp

_SENT_FOLDER = "Sent"

_INTEGRATION_TYPE = "imap"
_RE_PREFIX = "Re: "

EnsureFreshToken = Callable[
    [UserIntegration, UserIntegrationRepositoryPort], Awaitable[GmailIntegrationConfig]
]


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
        ensure_fresh_token: EnsureFreshToken = _real_ensure_fresh_token,
    ) -> None:
        """Recebe as portas de repositório por injeção.

        `email_repository` é usado para resolver o email original em replies
        (o caller passa `in_reply_to=<email_id>`, e o use case propaga
        `thread_id` e prefixa o `subject` com `Re:` quando ainda não estiver
        prefixado — REQ-005 email-inbox) e para persistir a mensagem enviada
        na pasta `Sent`, sem o que ela nunca apareceria em `list_emails`.

        `ensure_fresh_token` tem default = implementação real
        (`gmail_oauth.ensure_fresh_token`), só sobrescrita em teste — mesmo
        padrão de `EmailSyncWorker` (gmail-account-oauth-connection).
        """
        self._email_account_repository = email_account_repository
        self._integration_repository = integration_repository
        self._email_repository = email_repository
        self._ensure_fresh_token = ensure_fresh_token

    async def execute(
        self,
        *,
        user_id: str,
        account_id: str,
        to_addresses: list[str],
        subject: str,
        body_text: str | None = None,
        body_html: str | None = None,
        cc_addresses: list[str] | None = None,
        bcc_addresses: list[str] | None = None,
        in_reply_to: str | None = None,
        references: str | None = None,
        attachments: list[tuple[str, bytes, str]] | None = None,
    ) -> SendEmailResult:
        """Envia email via SMTP usando as credenciais da conta.

        `body_text` é opcional (email-send-html-only-by-default, REQ-010):
        pode ser `None` quando `body_html` é fornecido. Se ambos forem
        ausentes/vazios, levanta `ValueError("Send body required")` ANTES
        de chamar o SMTP e ANTES de upsertar a Sent row (mirror da regra
        422 do HTTP route).

        Args:
            in_reply_to: ID de um email do próprio `user_id` ao qual esta
                mensagem é reply. Quando informado, o use case propaga o
                `thread_id` desse email e prefixa o `subject` com `Re: `
                (idempotente — não duplica se já prefixado). O cabeçalho
                SMTP `In-Reply-To` é definido a partir do `message_id` do
                email original.

        Raises:
            ValueError: conta não encontrada, não pertence ao usuário,
                `in_reply_to` referencia email de outro user/inexistente,
                ou ambos `body_text` e `body_html` ausentes.
            SmtpAuthError: autenticação SMTP recusada.
            Exception: falhas de rede/timeout propagam sem embrulho.
        """
        # Resolve o par de bodies ANTES de qualquer side-effect (SMTP /
        # DB write) — uma única fonte de verdade para o que vai pro wire
        # e para o Sent row (design Decision 5 de
        # `email-send-html-only-by-default`).
        resolved_text, resolved_html = resolve_bodies(body_text, body_html)

        account = await self._email_account_repository.get(user_id, account_id)
        if account is None:
            raise ValueError("Email account not found")

        integration = await self._integration_repository.get(account.user_integration_id)
        if integration is None:
            raise ValueError("Email account integration credentials not found")

        config: ImapIntegrationConfig | GmailIntegrationConfig
        if integration.integration_type == "gmail":
            # REQ-003 (gmail-account-oauth-connection): refresca e persiste
            # o access_token ANTES do envio, se expirado.
            config = await self._ensure_fresh_token(
                integration, self._integration_repository
            )
        else:
            validated = validate_config(_INTEGRATION_TYPE, integration.config)
            assert isinstance(validated, ImapIntegrationConfig)
            config = validated

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
            body_text=resolved_text,
            body_html=resolved_html,
            in_reply_to=smtp_in_reply_to,
            references=smtp_references,
            attachments=attachments,
        )
        sent_at = datetime.now(UTC)

        # Persist the dispatched message so it appears in the account's Sent
        # folder — without this, `send_email` reports success but the email
        # is invisible to `list_emails`/`GET /api/email?folder=Sent` until
        # (if ever) the provider round-trips it back via IMAP sync.
        # Persiste o par RESOLVIDO (não os valores brutos do caller) para
        # que o Sent row reflita o que efetivamente foi enviado
        # (REQ-011 — body_text=None quando só HTML, body_text+html
        # gerado quando só plain).
        sender_address = config.smtp_username or config.imap_username
        sent_message = ParsedMessage(
            uid=message_id,
            message_id=message_id,
            folder=_SENT_FOLDER,
            from_address=sender_address,
            from_name=account.display_name,
            to_addresses=to_addresses,
            subject=final_subject,
            body_html=resolved_html,
            body_text=resolved_text,
            received_at=sent_at,
        )
        saved = await self._email_repository.upsert_email(account.id, sent_message)
        await self._email_repository.mark_read(user_id, saved.id)

        return SendEmailResult(
            message_id=message_id,
            sent_at=sent_at,
            thread_id=thread_id,
        )
