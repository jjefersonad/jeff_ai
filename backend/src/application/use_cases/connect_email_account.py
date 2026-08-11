"""Caso de uso: conectar uma conta de email genérica IMAP/SMTP.

REQ-001 do spec `email-account-management`: cria, numa única operação, a
`EmailAccount` (metadata) e a `UserIntegration` (`integration_type="imap"`)
que guarda os segredos — `config` é validado (`config_schemas.validate_config`)
E o login é verificado contra o servidor real (`verify_login`) ANTES de
qualquer persistência, para que um payload incompleto OU uma credencial
recusada pelo servidor não deixe nenhuma das duas linhas gravada — "fail
fast, don't store known-bad credentials" (task
`email-client-imap-mvp-task-accounts-2`).
"""
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from src.application.integrations.config_schemas import (
    ImapIntegrationConfig,
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

_INTEGRATION_TYPE = "imap"

VerifyLogin = Callable[[ImapIntegrationConfig], Awaitable[None]]


class ConnectEmailAccount:
    """Valida config + login IMAP e persiste a conta + suas credenciais."""

    def __init__(
        self,
        *,
        repository: EmailAccountRepositoryPort,
        integration_repository: UserIntegrationRepositoryPort,
        verify_login: VerifyLogin,
    ) -> None:
        """Recebe as portas de repositório e o verificador de login por injeção.

        `verify_login` é obrigatório (sem default) para que nenhum caller
        esqueça de checar o login antes de persistir — ver
        `src.infrastructure.email.imap_client.verify_imap_login` para a
        implementação real usada em produção.
        """
        self._repository = repository
        self._integration_repository = integration_repository
        self._verify_login = verify_login

    async def execute(
        self, *, user_id: str, display_name: str, config: dict[str, object]
    ) -> EmailAccount:
        """Valida `config` e o login, então cria `UserIntegration` + `EmailAccount`.

        Raises:
            pydantic.ValidationError: se `config` não bater com
                `ImapIntegrationConfig`.
            Exception: o que `verify_login` levantar (tipicamente
                `ImapAuthError` para credencial recusada). Em ambos os
                casos, nenhuma das duas linhas é persistida.
        """
        validated = validate_config(_INTEGRATION_TYPE, config)
        assert isinstance(validated, ImapIntegrationConfig)
        await self._verify_login(validated)

        now = datetime.now(UTC)
        integration = UserIntegration(
            id=str(uuid.uuid4()),
            user_id=user_id,
            integration_type=_INTEGRATION_TYPE,
            config=validated.model_dump(),
            created_at=now,
            updated_at=now,
        )
        await self._integration_repository.save(integration)

        account = EmailAccount(
            id=str(uuid.uuid4()),
            user_id=user_id,
            user_integration_id=integration.id,
            display_name=display_name,
            status=EmailAccountStatus.CONNECTED,
            created_at=now,
            updated_at=now,
        )
        return await self._repository.create(account)
