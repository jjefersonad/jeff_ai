"""Poll loop do sync worker (`email-client-imap-mvp-task-sync-3`).

`EmailSyncWorker.poll_once` roda uma iteração: varre TODAS as
`email_accounts` (`EmailAccountRepositoryPort.list_all`), pula as com
`is_active=false` (REQ-005), busca mensagens novas via `fetch_messages`
(tipicamente `imap_client.fetch_new_messages`) e persiste via
`EmailRepositoryPort.upsert_email` (task sync-2).

Para cada mensagem, resolve o contato do CRM correspondente por
`from_address` (`CrmRepositoryPort.get_contact_by_email`, task inbox-4,
REQ-006) e passa o `contact_id` para `upsert_email`. Sem match, a
mensagem é persistida normalmente com `contact_id=None` — nenhum erro é
levantado.

Com contato resolvido, também chama `ClassifyEmailByContact`
(`sales-pipeline-via-agent-task-backend-email-1`, REQ-005) passando o
`Contact` já obtido — evita um segundo `get_contact_by_email` idêntico. Se
o contato tiver um deal ativo (`stage NOT IN ('won','lost')`), grava uma
nota `crm_notes(source='system')` no deal; o estágio nunca é alterado por
esse caminho.

Em falha de autenticação (`ImapAuthError`), marca `status="error"` sem
tocar a linha `user_integrations` — para contas IMAP a garantia continua
estrutural (nenhuma chamada a `save` nesse caminho). Para contas Gmail
(gmail-account-oauth-connection), `ensure_fresh_token` É chamado antes do
fetch e PODE persistir um `access_token` renovado via
`integration_repository.save(...)` quando o token expirou — se o refresh
em si falhar (`RefreshTokenRevokedError`), nada é persistido e a conta cai
no mesmo `_mark_error`, mas o caminho de sucesso do refresh não é mais
"nunca toca user_integrations" para esse provider.

Defesa contra `user_integrations` malformada: uma `email_accounts` pode
estar apontando para uma `user_integrations` com `integration_type` fora
de `{"imap", "gmail"}` (ex.: legados `smtp` stub com `config={}` criados
via `POST /api/integrations` antes deste MVP) ou com `config` que não bate
com `ImapIntegrationConfig`/`GmailIntegrationConfig` (ex.: truncado por
migration parcial). Nesses casos, a conta é marcada `status="error"` e o
loop segue — uma conta ruim não pode derrubar o worker inteiro (bug em
produção 2026-08-10: `pydantic.ValidationError` em
`ImapIntegrationConfig(**{})` estava fora do `try/except` e matava o
`poll_once`).

Watermarks (último UID visto por conta+pasta) ficam em memória do
processo, não persistidos: o worker é um único container de vida longa
(design Decision 2 de `email-client-imap-mvp`), e reprocessar mensagens já
vistas após um restart é inofensivo — `upsert_email` é idempotente por
`(email_account_id, message_id)`.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from src.application.integrations.config_schemas import (
    GmailIntegrationConfig,
    ImapIntegrationConfig,
)
from src.application.ports.crm_repository import CrmRepositoryPort
from src.application.ports.email_account_repository import (
    EmailAccountRepositoryPort,
)
from src.application.ports.email_repository import EmailRepositoryPort
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.application.use_cases.classify_email_by_contact import (
    ClassifyEmailByContact,
)
from src.domain.email import EmailAccount, EmailAccountStatus, ParsedMessage
from src.domain.integrations import UserIntegration
from src.infrastructure.email.gmail_oauth import (
    ensure_fresh_token as _real_ensure_fresh_token,
)

logger = logging.getLogger(__name__)

FetchMessages = Callable[
    [ImapIntegrationConfig | GmailIntegrationConfig, str, int],
    Awaitable[list[ParsedMessage]],
]
EnsureFreshToken = Callable[
    [UserIntegration, UserIntegrationRepositoryPort], Awaitable[GmailIntegrationConfig]
]

#: v1 sincroniza apenas a caixa de entrada principal — descoberta/sync de
#: pastas customizadas por provedor é não-objetivo do MVP (design
#: email-client-imap-mvp, Non-Goals).
_SYNCED_FOLDERS = ("INBOX",)


class EmailSyncWorker:
    """Uma iteração (`poll_once`) do loop do `email_sync_worker`."""

    def __init__(
        self,
        *,
        account_repository: EmailAccountRepositoryPort,
        integration_repository: UserIntegrationRepositoryPort,
        email_repository: EmailRepositoryPort,
        crm_repository: CrmRepositoryPort,
        fetch_messages: FetchMessages,
        ensure_fresh_token: EnsureFreshToken = _real_ensure_fresh_token,
    ) -> None:
        """Recebe as portas de repositório e o fetch client por injeção.

        `ensure_fresh_token` tem default = implementação real
        (`gmail_oauth.ensure_fresh_token`), só sobrescrita em teste — mesmo
        padrão de `fetch_messages`, mas com default para não exigir que
        todo call site (produção e testes já existentes) passe um valor.
        """
        self._account_repository = account_repository
        self._integration_repository = integration_repository
        self._email_repository = email_repository
        self._crm_repository = crm_repository
        self._fetch_messages = fetch_messages
        self._ensure_fresh_token = ensure_fresh_token
        self._classify_by_contact = ClassifyEmailByContact(repository=crm_repository)
        self._watermarks: dict[tuple[str, str], int] = {}

    async def poll_once(self) -> None:
        """Varre todas as contas e sincroniza as `is_active=true` (REQ-005)."""
        accounts = await self._account_repository.list_all()
        for account in accounts:
            if not account.is_active:
                continue
            await self._poll_account(account)

    async def _poll_account(self, account: EmailAccount) -> None:
        integration = await self._integration_repository.get(account.user_integration_id)
        if integration is None:
            logger.warning(
                "email_accounts id=%s sem user_integrations vinculada — pulada.",
                account.id,
            )
            return

        if integration.integration_type not in ("imap", "gmail"):
            # Defesa contra `user_integrations` que apontem para um tipo
            # diferente (ex.: legados `smtp` stub com `config={}` criados via
            # `POST /api/integrations` antes do MVP). Sem isso, o `pydantic
            # ValidationError` em `ImapIntegrationConfig(**integration.config)`
            # derruba o loop inteiro do worker.
            await self._mark_error(
                account,
                f"integration_type={integration.integration_type!r} "
                "(esperado 'imap' ou 'gmail')",
            )
            return

        try:
            config: ImapIntegrationConfig | GmailIntegrationConfig
            if integration.integration_type == "gmail":
                # REQ-003 (gmail-account-oauth-connection): refresca e
                # persiste o access_token ANTES do fetch, se expirado.
                config = await self._ensure_fresh_token(
                    integration, self._integration_repository
                )
            else:
                config = ImapIntegrationConfig(**integration.config)
            for folder in _SYNCED_FOLDERS:
                await self._sync_folder(account, config, folder)
        except Exception as exc:
            # Loga a mensagem do erro sem a credencial (defesa em profundidade
            # — REQ-003 nunca vaza plaintext em campo user-visible). O
            # `exc.args`/`str(exc)` daioimaplib não inclui senha.
            await self._mark_error(account, f"{exc.__class__.__name__}: {exc}")
            return

        account.status = EmailAccountStatus.CONNECTED
        account.last_synced_at = datetime.now(UTC)
        account.updated_at = account.last_synced_at
        await self._account_repository.update(account)

    async def _sync_folder(
        self,
        account: EmailAccount,
        config: ImapIntegrationConfig | GmailIntegrationConfig,
        folder: str,
    ) -> None:
        key = (account.id, folder)
        watermark = self._watermarks.get(key, 0)
        messages = await self._fetch_messages(config, folder, watermark)
        for message in messages:
            contact = await self._crm_repository.get_contact_by_email(
                account.user_id, message.from_address
            )
            contact_id = contact.id if contact is not None else None
            await self._email_repository.upsert_email(
                account.id, message, contact_id=contact_id
            )
            if contact is not None:
                await self._classify_by_contact.execute(
                    user_id=account.user_id,
                    sender_email=message.from_address,
                    subject=message.subject or "",
                    contact=contact,
                )
            self._watermarks[key] = max(self._watermarks.get(key, 0), int(message.uid))

    async def _mark_error(self, account: EmailAccount, reason: str) -> None:
        """Marca `status="error"` em `email_accounts` sem tocar `user_integrations`.

        Loga só a classe/motivo do erro — REQ-003 nunca persiste plaintext
        de credencial nem o stack trace completo em campo user-visible.
        """
        logger.warning(
            "email_accounts id=%s: %s — status=error.",
            account.id,
            reason,
        )
        account.status = EmailAccountStatus.ERROR
        account.updated_at = datetime.now(UTC)
        await self._account_repository.update(account)
