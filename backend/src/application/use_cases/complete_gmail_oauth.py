"""Caso de uso: completar o fluxo OAuth2 do Google, criando a conta Gmail.

REQ-002 do spec `gmail-oauth-connection`. `exchange_code_for_tokens` é
injetado — não importado direto de `infrastructure/` — mesmo padrão de
`VerifyLogin`/`StartGmailOAuth`. Espelha o "fail fast, don't store
known-bad credentials" de `ConnectEmailAccount`: se a troca do `code`
falhar (ex.: `MissingRefreshTokenError`), nenhuma das duas linhas
(`user_integrations`/`email_accounts`) é persistida.
"""
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from src.application.integrations.config_schemas import (
    GmailIntegrationConfig,
    validate_config,
)
from src.application.ports.email_account_repository import (
    EmailAccountRepositoryPort,
)
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.domain.email import EmailAccount, EmailAccountStatus
from src.domain.integrations import UserIntegration

_INTEGRATION_TYPE = "gmail"


class GmailTokenExchangeResult(Protocol):
    """Forma estrutural do resultado de `exchange_code_for_tokens` — sem
    importar o dataclass concreto de `infrastructure/email/gmail_oauth.py`."""

    access_token: str
    refresh_token: str
    expires_in: int
    email_address: str


ExchangeCodeForTokens = Callable[[str], Awaitable[GmailTokenExchangeResult]]


class CompleteGmailOAuth:
    """Troca `code` por tokens e persiste `UserIntegration` + `EmailAccount` (`provider="gmail"`)."""

    def __init__(
        self,
        *,
        repository: EmailAccountRepositoryPort,
        integration_repository: UserIntegrationRepositoryPort,
        exchange_code_for_tokens: ExchangeCodeForTokens,
    ) -> None:
        """Recebe as portas de repositório e o exchanger por injeção (ver docstring do módulo)."""
        self._repository = repository
        self._integration_repository = integration_repository
        self._exchange_code_for_tokens = exchange_code_for_tokens

    async def execute(self, *, user_id: str, code: str) -> EmailAccount:
        """Troca `code` pelos tokens Gmail e persiste a conta.

        Se o usuário já tem uma `EmailAccount` `provider="gmail"` ativa para
        o mesmo `email_address` (REQ-005), atualiza os tokens dessa conta
        existente em vez de criar uma segunda linha.

        Raises:
            MissingRefreshTokenError: propagada de `exchange_code_for_tokens`
                (Google respondeu sem `refresh_token`) — nenhuma linha é
                persistida.
        """
        tokens = await self._exchange_code_for_tokens(code)

        now = datetime.now(UTC)
        config_payload = {
            "email_address": tokens.email_address,
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "token_expiry": (now + timedelta(seconds=tokens.expires_in)).isoformat(),
        }
        validated = validate_config(_INTEGRATION_TYPE, config_payload)
        assert isinstance(validated, GmailIntegrationConfig)

        existing = await self._find_existing_account(user_id, tokens.email_address)
        if existing is not None:
            return await self._reconnect(existing, validated, now)
        return await self._connect_new(user_id, tokens.email_address, validated, now)

    async def _find_existing_account(
        self, user_id: str, email_address: str
    ) -> EmailAccount | None:
        accounts = await self._repository.list_by_user(user_id)
        for account in accounts:
            if account.provider == _INTEGRATION_TYPE and account.display_name == email_address:
                return account
        return None

    async def _reconnect(
        self, account: EmailAccount, validated: GmailIntegrationConfig, now: datetime
    ) -> EmailAccount:
        """Atualiza os tokens de uma conta Gmail já existente, reconectando-a
        (`status="connected"`) mesmo que estivesse `"error"` (REQ-005)."""
        existing_integration = await self._integration_repository.get(
            account.user_integration_id
        )
        created_at = existing_integration.created_at if existing_integration else now

        account.status = EmailAccountStatus.CONNECTED
        account.updated_at = now
        updated = await self._repository.update(account)
        assert updated is not None  # own account just listed — can't miss

        await self._integration_repository.save(
            UserIntegration(
                id=account.user_integration_id,
                user_id=account.user_id,
                integration_type=_INTEGRATION_TYPE,
                config=validated.model_dump(mode="json"),
                created_at=created_at,
                updated_at=now,
            )
        )
        return updated

    async def _connect_new(
        self,
        user_id: str,
        email_address: str,
        validated: GmailIntegrationConfig,
        now: datetime,
    ) -> EmailAccount:
        integration = UserIntegration(
            id=str(uuid.uuid4()),
            user_id=user_id,
            integration_type=_INTEGRATION_TYPE,
            config=validated.model_dump(mode="json"),
            created_at=now,
            updated_at=now,
        )
        await self._integration_repository.save(integration)

        account = EmailAccount(
            id=str(uuid.uuid4()),
            user_id=user_id,
            user_integration_id=integration.id,
            display_name=email_address,
            provider=_INTEGRATION_TYPE,
            status=EmailAccountStatus.CONNECTED,
            created_at=now,
            updated_at=now,
        )
        return await self._repository.create(account)
