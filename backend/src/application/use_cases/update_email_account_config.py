"""Caso de uso: editar as configurações de conexão (IMAP/SMTP) de uma conta de email já conectada.

REQ-002 do spec `email-account-edit-connection` + REQ-006 do delta do spec
`email-account-management`. Diferente de `UpdateEmailAccount` (que edita só
`display_name`/`is_active`), este caso de uso:

- recebe um `config_patch` parcial cujas chaves sobrescrevem o `config` da
  `UserIntegration` (`integration_type="imap"`) associada à `EmailAccount`
  — chaves ausentes são mantidas, e a ausência/blank-ness de uma senha
  significa "manter a senha atual";
- re-valida o `config` resultante contra `ImapIntegrationConfig` (via
  `validate_config`) e re-verifica o login IMAP via `verify_login`
  (verificação IMAP-only — não há `verify_smtp_login`; uma senha SMTP
  errada é detectada no próximo envio, mesmo comportamento de
  `ConnectEmailAccount`);
- persiste a `EmailAccount` e a `UserIntegration` na ordem "conta primeiro,
  credencial depois" — monta uma NOVA `UserIntegration` (com o `config` mergeado
  re-validado) e só atribui/serializa via `save` no final, de modo que uma falha
  em qualquer `_repository.update` OU `_integration_repository.save` não
  deixa nenhum estado mutado: a checagem de ownership, o smoke check e a
  validação acontecem ANTES de qualquer escrita (ver `execute` para a ordem
  exata).

Ownership: o `EmailAccountRepositoryPort.get(user_id, account_id)` já é
escopado a `user_id`; o `UserIntegrationRepositoryPort.get` NÃO é, então o
caso de uso verifica `integration.user_id == user_id` como defesa em
profundidade (cenário de corrupção de dados ou admin override).
"""
from __future__ import annotations

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

# Reuse the same callable type used by `connect_email_account` so swapping
# the verify_login implementation in tests and in production is a drop-in.
from src.application.use_cases.connect_email_account import VerifyLogin
from src.domain.email import EmailAccount, EmailAccountStatus
from src.domain.integrations import UserIntegration

_INTEGRATION_TYPE = "imap"


class UpdateEmailAccountConfig:
    """Edita as configurações de conexão de uma conta de email própria.

    Diferente de `UpdateEmailAccount` (que edita apenas `display_name`/
    `is_active`), esta classe trata da mudança de host/porta/usuário/senha
    IMAP e SMTP — re-valida o `config` resultante e re-verifica o login
    IMAP antes de qualquer persistência. As senhas são omitidas (ou
    string vazia) quando o usuário não quer trocá-las.
    """

    def __init__(
        self,
        *,
        repository: EmailAccountRepositoryPort,
        integration_repository: UserIntegrationRepositoryPort,
        verify_login: VerifyLogin,
    ) -> None:
        """Recebe as portas de repositório e o verificador de login por injeção."""
        self._repository = repository
        self._integration_repository = integration_repository
        self._verify_login = verify_login

    async def execute(
        self,
        *,
        user_id: str,
        account_id: str,
        config_patch: dict[str, object],
        display_name: str | None,
    ) -> EmailAccount | None:
        """Aplica o patch e devolve a `EmailAccount` atualizada; `None` se miss.

        Ordem das operações (fail-fast — todas as checagens antes de qualquer
        escrita):
          1. Carrega `EmailAccount` filtrado por `(id, user_id)`. Se miss,
             retorna `None` (handler mapeia para 404).
          2. Carrega a `UserIntegration` associada e verifica
             `integration.user_id == user_id` (defesa em profundidade).
          3. Monta o `config` resultante = merge do patch sobre o `config`
             atual (plaintext em memória — a cifra fica no adapter).
          4. Re-valida via `validate_config("imap", merged)`. Falha
             `pydantic.ValidationError` propaga sem escrita.
          5. Re-verifica o login IMAP via `verify_login(validated)`. Falha
             propaga sem escrita.
          6. Persiste: atualiza a `EmailAccount` (display_name, status,
             updated_at) e salva a `UserIntegration` com o `config` novo
             (o adapter cifra na saída).

        Raises:
            pydantic.ValidationError: se o `config` mergeado não bater com
                o schema `ImapIntegrationConfig`.
            Exception: o que `verify_login` levantar (tipicamente
                `ImapAuthError` para credencial IMAP recusada). Em ambos
                os casos, nenhum write acontece.
        """
        account = await self._repository.get(user_id, account_id)
        if account is None:
            return None

        integration = await self._integration_repository.get(account.user_integration_id)
        if integration is None or integration.user_id != user_id:
            return None

        merged_config: dict[str, object] = {**integration.config, **config_patch}
        validated = validate_config(_INTEGRATION_TYPE, merged_config)
        assert isinstance(validated, ImapIntegrationConfig)
        await self._verify_login(validated)

        now = datetime.now(UTC)
        if display_name is not None:
            account.display_name = display_name
        account.status = EmailAccountStatus.CONNECTED
        account.updated_at = now

        # Build a new `UserIntegration` with the merged/validated config so
        # the in-memory original is left untouched if `save` raises. This
        # matches the "build then save" pattern in `ConnectEmailAccount`
        # and gives the caller a clear "writes nothing" semantic for the
        # credentials when the underlying adapter fails mid-write.
        new_integration = UserIntegration(
            id=integration.id,
            user_id=integration.user_id,
            integration_type=integration.integration_type,
            config=validated.model_dump(),
            created_at=integration.created_at,
            updated_at=now,
        )

        # Persist the account first; if `_integration_repository.save` then
        # raises, the in-memory `integration` (the one held by the caller)
        # is unchanged because we never assigned to `integration.config`
        # directly — we mutated `new_integration` and passed that to `save`.
        # The `_repository.update` is `(id, user_id)`-scoped and will return
        # `None` on miss; that None propagates as the use-case return value
        # (handler → 404). The integration.save either succeeds or raises.
        updated = await self._repository.update(account)
        if updated is None:
            return None
        await self._integration_repository.save(new_integration)
        return updated
