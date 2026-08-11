"""Rotas REST de `EmailAccount` (`email-client-imap-mvp-task-accounts-3`).

Mesmo molde de `integrations_router.py`: dependency-factories constroem os
repositórios Postgres por requisição a partir de `POSTGRES_URI`. `user_id` é
sempre resolvido do `User` de `require_auth`, nunca de um campo do corpo da
requisição (REQ-001/REQ-002 do spec `email-account-management`).

`GET`/`PUT`/`DELETE /api/email/accounts/{id}` devolvem 404 tanto para id
inexistente quanto para conta de outro usuário — REQ-002 exige não revelar
existência, e trata delete pela mesma regra (diferente do padrão de "204
silencioso sempre" usado em `integrations_router.py` para Telegram/WhatsApp).

`POST /api/email/accounts` valida o config IMAP/SMTP E verifica o login
contra o servidor real (`ConnectEmailAccount`/`verify_imap_login`) ANTES de
persistir qualquer linha — payload malformado vira 422, credencial recusada
pelo servidor vira 400, nenhum dos dois casos deixa `email_accounts` ou
`user_integrations` gravados (REQ-001, tasks accounts-1/accounts-2).
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError

from src.application.integrations.config_schemas import UnknownIntegrationTypeError
from src.application.ports.email_account_repository import (
    EmailAccountRepositoryPort,
)
from src.application.ports.email_repository import EmailRepositoryPort
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.application.use_cases.connect_email_account import (
    ConnectEmailAccount,
    VerifyLogin,
)
from src.application.use_cases.delete_email_account import DeleteEmailAccount
from src.application.use_cases.get_email import GetEmail
from src.application.use_cases.get_email_account import GetEmailAccount
from src.application.use_cases.list_email_accounts import ListEmailAccounts
from src.application.use_cases.list_emails import ListEmails
from src.application.use_cases.search_emails import SearchEmails
from src.application.use_cases.send_email import SendEmail
from src.application.use_cases.update_email_account import UpdateEmailAccount
from src.application.use_cases.update_email_account_config import (
    UpdateEmailAccountConfig,
)
from src.domain.email import Email, EmailAccount
from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.users import User
from src.infrastructure.email.imap_client import ImapAuthError, verify_imap_login
from src.infrastructure.email.smtp_client import SmtpAuthError
from src.infrastructure.persistence.email_account_repository import (
    PostgresEmailAccountRepository,
)
from src.infrastructure.persistence.email_repository import PostgresEmailRepository
from src.infrastructure.persistence.user_integrations_repository import (
    PostgresUserIntegrationRepository,
)

router = APIRouter()


def _email_account_repository() -> EmailAccountRepositoryPort:
    """Constrói o repositório de contas a partir de `POSTGRES_URI`."""
    return PostgresEmailAccountRepository(os.environ["POSTGRES_URI"])


def _user_integration_repository() -> UserIntegrationRepositoryPort:
    """Constrói o repositório de credenciais a partir de `POSTGRES_URI`."""
    return PostgresUserIntegrationRepository(os.environ["POSTGRES_URI"])


def _verify_imap_login() -> VerifyLogin:
    """Devolve o verificador de login IMAP real (sobrescrito por fakes em teste)."""
    return verify_imap_login


def _email_repository() -> EmailRepositoryPort:
    """Constrói o repositório de emails a partir de `POSTGRES_URI`."""
    return PostgresEmailRepository(os.environ["POSTGRES_URI"])


class EmailAccountConnectRequest(BaseModel):
    """Corpo de `POST /api/email/accounts`. Nenhum campo de ownership."""

    display_name: str
    imap_host: str
    imap_port: int
    imap_username: str
    imap_password: str
    smtp_host: str
    smtp_port: int
    smtp_username: str | None = None
    smtp_password: str | None = None


class EmailAccountUpdateRequest(BaseModel):
    """Corpo de `PUT /api/email/accounts/{id}` — só metadata, nunca credenciais."""

    display_name: str | None = None
    is_active: bool | None = None


class EmailAccountUpdateConfigRequest(BaseModel):
    """Corpo de `PATCH /api/email/accounts/{id}` — edita configuração de conexão.

    Todos os campos são opcionais. O endpoint filtra `None` antes de
    chamar o use case, então chaves ausentes no body NÃO sobrescrevem o
    valor atual (REQ-002 do spec `email-account-edit-connection`).
    Senhas vazias (`""`) também são filtradas — o endpoint trata
    `imap_password`/`smtp_password` ausentes OU `""` como "manter a senha
    atual".
    """

    display_name: str | None = None
    imap_host: str | None = None
    imap_port: int | None = None
    imap_username: str | None = None
    imap_password: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None


class SendEmailRequest(BaseModel):
    """Corpo de `POST /api/email/send`.

    `in_reply_to` é o ID (UUID) de um email já sincronizado do próprio
    user; o use case propaga `thread_id` e prefixa `subject` com `Re:`
    automaticamente (REQ-005 email-inbox).
    """

    account_id: str
    to_addresses: list[str]
    subject: str
    body_text: str
    body_html: str | None = None
    cc_addresses: list[str] | None = None
    bcc_addresses: list[str] | None = None
    in_reply_to: str | None = None
    references: str | None = None


class SendEmailResponse(BaseModel):
    """Resposta de `POST /api/email/send`."""

    message_id: str
    sent_at: datetime
    thread_id: str | None = None
    subject: str | None = None


class EmailAccountResponse(BaseModel):
    """Contrato HTTP de uma `EmailAccount` — nunca inclui credenciais.

    Inclui o subset não-secreto da configuração de conexão (host/porta/
    username IMAP e SMTP) para que o frontend possa reusar o
    `ConnectAccountDialog` em modo `edit` sem precisar de um GET
    adicional. **Senhas (imap_password/smtp_password) NUNCA são
    retornadas** — o frontend as trata como "manter a senha atual"
    quando vierem em branco no PATCH (REQ-002 do spec
    `email-account-edit-connection`).
    """

    id: str
    user_id: str
    provider: str
    display_name: str
    status: str
    last_synced_at: datetime | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    imap_host: str | None = None
    imap_port: int | None = None
    imap_username: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None


async def _to_response(
    account: EmailAccount,
    integration_repo: UserIntegrationRepositoryPort | None = None,
) -> EmailAccountResponse:
    """Serializa `EmailAccount` para o contrato HTTP.

    Quando recebe `integration_repo`, carrega a `UserIntegration`
    associada para preencher os campos não-secretos de configuração
    IMAP/SMTP (host/porta/username). Senhas nunca são extraídas.

    Quando `integration_repo` é `None` (call sites legados que só
    tinham o `EmailAccountRepositoryPort`), os campos de configuração
    ficam `None` — comportamento equivalente ao anterior, preservado
    para que as rotas que não precisam de config não sejam forçadas a
    injetar a segunda dependência.
    """
    config: dict[str, object] | None = None
    if integration_repo is not None:
        integration = await integration_repo.get(account.user_integration_id)
        # Defesa em profundidade: garante que a integração pertence ao
        # mesmo user antes de devolver a config (impossível na rota
        # correta — `integration_repo.get` é escopada só por id).
        if integration is not None and integration.user_id == account.user_id:
            config = integration.config

    def _cfg_value(key: str) -> Any:
        """Lê `config[key]` independentemente do tipo armazenado.

        O domínio (`UserIntegration.config`) é tipicamente um `dict[str,
        object]` com mistura de strings e inteiros (e.g. `imap_port: 993`
        vs `imap_password: "secret"`). O adapter Postgres serializa tudo
        via `json.dumps` antes de cifrar, então valores numéricos são
        preservados como JSON ints e o `decrypt_config` os devolve como
        ints. Esta função aceita os dois formatos para tolerância.
        """
        if config is None or key not in config:
            return None
        return config[key]

    def cfg_str(key: str) -> str | None:
        value = _cfg_value(key)
        if value is None:
            return None
        return value if isinstance(value, str) else None

    def cfg_int(key: str) -> int | None:
        value = _cfg_value(key)
        if value is None:
            return None
        if isinstance(value, bool):
            return None  # bool é subclass de int; evita confusão com True/False
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return None
        return None

    return EmailAccountResponse(
        id=account.id,
        user_id=account.user_id,
        provider=account.provider,
        display_name=account.display_name,
        status=account.status.value,
        last_synced_at=account.last_synced_at,
        is_active=account.is_active,
        created_at=account.created_at,
        updated_at=account.updated_at,
        imap_host=cfg_str("imap_host"),
        imap_port=cfg_int("imap_port"),
        imap_username=cfg_str("imap_username"),
        smtp_host=cfg_str("smtp_host"),
        smtp_port=cfg_int("smtp_port"),
        smtp_username=cfg_str("smtp_username"),
    )


class EmailResponse(BaseModel):
    """Contrato HTTP de um `Email` — inclui body_html/body_text."""

    id: str
    email_account_id: str
    message_id: str
    thread_id: str | None
    folder: str
    from_address: str
    from_name: str | None
    to_addresses: list[str]
    cc_addresses: list[str]
    bcc_addresses: list[str]
    subject: str | None
    body_html: str | None
    body_text: str | None
    is_read: bool
    is_starred: bool
    has_attachments: bool
    contact_id: str | None
    received_at: datetime
    created_at: datetime


def _to_email_response(email: Email) -> EmailResponse:
    return EmailResponse(
        id=email.id,
        email_account_id=email.email_account_id,
        message_id=email.message_id,
        thread_id=email.thread_id,
        folder=email.folder,
        from_address=email.from_address,
        from_name=email.from_name,
        to_addresses=email.to_addresses,
        cc_addresses=email.cc_addresses,
        bcc_addresses=email.bcc_addresses,
        subject=email.subject,
        body_html=email.body_html,
        body_text=email.body_text,
        is_read=email.is_read,
        is_starred=email.is_starred,
        has_attachments=email.has_attachments,
        contact_id=email.contact_id,
        received_at=email.received_at,
        created_at=email.created_at,
    )


@router.get("/api/email/accounts")
async def list_email_accounts_endpoint(
    user: User | None = Depends(require_auth),
    repo: EmailAccountRepositoryPort = Depends(_email_account_repository),
    integration_repo: UserIntegrationRepositoryPort = Depends(
        _user_integration_repository
    ),
) -> list[EmailAccountResponse]:
    """REQ-002: escopado ao dono — nunca lista contas de outro usuário.

    Inclui os campos não-secretos da configuração (host/porta/username
    IMAP/SMTP) para que o frontend possa abrir o diálogo de edição de
    conexão sem precisar de um GET adicional por conta.
    """
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    accounts = await ListEmailAccounts(repository=repo).execute(user_id=user.id)
    return [await _to_response(a, integration_repo) for a in accounts]


@router.post("/api/email/accounts", status_code=201)
async def connect_email_account_endpoint(
    body: EmailAccountConnectRequest,
    user: User | None = Depends(require_auth),
    repo: EmailAccountRepositoryPort = Depends(_email_account_repository),
    integration_repo: UserIntegrationRepositoryPort = Depends(
        _user_integration_repository
    ),
    verify_login: VerifyLogin = Depends(_verify_imap_login),
) -> EmailAccountResponse:
    """REQ-001: valida config + login antes de persistir; nunca ecoa credenciais."""
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    config = body.model_dump(exclude={"display_name"})
    use_case = ConnectEmailAccount(
        repository=repo,
        integration_repository=integration_repo,
        verify_login=verify_login,
    )
    try:
        account = await use_case.execute(
            user_id=user.id, display_name=body.display_name, config=config
        )
    except (UnknownIntegrationTypeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ImapAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _to_response(account, integration_repo)


@router.get("/api/email/accounts/{account_id}")
async def get_email_account_endpoint(
    account_id: str,
    user: User | None = Depends(require_auth),
    repo: EmailAccountRepositoryPort = Depends(_email_account_repository),
    integration_repo: UserIntegrationRepositoryPort = Depends(
        _user_integration_repository
    ),
) -> EmailAccountResponse:
    """REQ-002: 404 tanto para id inexistente quanto para conta de outro usuário."""
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    account = await GetEmailAccount(repository=repo).execute(
        user_id=user.id, account_id=account_id
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Email account not found")
    return await _to_response(account, integration_repo)


@router.put("/api/email/accounts/{account_id}")
async def update_email_account_endpoint(
    account_id: str,
    body: EmailAccountUpdateRequest,
    user: User | None = Depends(require_auth),
    repo: EmailAccountRepositoryPort = Depends(_email_account_repository),
    integration_repo: UserIntegrationRepositoryPort = Depends(
        _user_integration_repository
    ),
) -> EmailAccountResponse:
    """REQ-002: dono edita `display_name`/`is_active`; cross-user recebe 404."""
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    updated = await UpdateEmailAccount(repository=repo).execute(
        user_id=user.id,
        account_id=account_id,
        display_name=body.display_name,
        is_active=body.is_active,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Email account not found")
    return await _to_response(updated, integration_repo)


@router.patch("/api/email/accounts/{account_id}")
async def update_email_account_config_endpoint(
    account_id: str,
    body: EmailAccountUpdateConfigRequest,
    user: User | None = Depends(require_auth),
    repo: EmailAccountRepositoryPort = Depends(_email_account_repository),
    integration_repo: UserIntegrationRepositoryPort = Depends(
        _user_integration_repository
    ),
    verify_login: VerifyLogin = Depends(_verify_imap_login),
) -> EmailAccountResponse:
    """REQ-002 do spec `email-account-edit-connection`.

    Edita as configurações de conexão (host/porta/usuário/senha IMAP e
    SMTP, display_name) de uma conta própria. Senhas ausentes OU `""`
    são tratadas como "manter a senha atual" pelo use case
    `UpdateEmailAccountConfig`. Cross-user e id inexistente recebem 404
    (mesmo corpo, sem vazar existência).
    """
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Filtra chaves ausentes: Pydantic preenche com `None` quando o campo
    # não vem no JSON. Como `UpdateEmailAccountConfig` faz
    # `{**integration.config, **config_patch}`, sobrescrever com `None`
    # quebraria o `min_length=1` da validação IMAP — então só repassamos
    # os campos realmente enviados.
    raw_patch = body.model_dump(exclude_none=True)
    config_patch = {
        key: value
        for key, value in raw_patch.items()
        if key != "display_name"
    }
    # Senhas ausentes OU string vazia significam "manter a senha atual"
    # (REQ-002 email-account-edit-connection). Removemos do patch antes
    # de mandar pro use case — ele preserva chaves ausentes.
    for password_field in ("imap_password", "smtp_password"):
        if password_field in config_patch and config_patch[password_field] == "":
            del config_patch[password_field]
    use_case = UpdateEmailAccountConfig(
        repository=repo,
        integration_repository=integration_repo,
        verify_login=verify_login,
    )
    try:
        updated = await use_case.execute(
            user_id=user.id,
            account_id=account_id,
            config_patch=config_patch,
            display_name=body.display_name,
        )
    except (UnknownIntegrationTypeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ImapAuthError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Email account not found")
    return await _to_response(updated, integration_repo)


# `response_model=None` explícito: sem isso, FastAPI infere `NoneType` a partir
# de `-> None`, que dispara a assertion de "status 204 não pode ter corpo"
# (mesmo motivo documentado em `integrations_router.delete_integration_endpoint`).
@router.delete(
    "/api/email/accounts/{account_id}", status_code=204, response_model=None
)
async def delete_email_account_endpoint(
    account_id: str,
    user: User | None = Depends(require_auth),
    repo: EmailAccountRepositoryPort = Depends(_email_account_repository),
    integration_repo: UserIntegrationRepositoryPort = Depends(
        _user_integration_repository
    ),
) -> None:
    """REQ-002/REQ-004: dono remove conta + credencial; cross-user recebe 404."""
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    deleted = await DeleteEmailAccount(
        repository=repo, integration_repository=integration_repo
    ).execute(user_id=user.id, account_id=account_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Email account not found")


# ── Email inbox endpoints (inbox-2) ───────────────────────────────────────────


@router.get("/api/email")
async def list_emails_endpoint(
    account_id: str | None = None,
    folder: str | None = "INBOX",
    limit: int = 20,
    offset: int = 0,
    user: User | None = Depends(require_auth),
    repo: EmailRepositoryPort = Depends(_email_repository),
) -> list[EmailResponse]:
    """REQ-001: list emails scoped to the authenticated user's account.

    Sem `account_id` retorna o inbox unificado do user; sem `folder`
    também desce a granularidade para todas as pastas. `account_id` sem
    `folder` filtra só pela conta (todas as pastas dessa conta).
    """
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if limit > 100:
        limit = 100
    if offset < 0:
        offset = 0
    emails = await ListEmails(repository=repo).execute(
        user_id=user.id, account_id=account_id, folder=folder, limit=limit, offset=offset
    )
    return [_to_email_response(e) for e in emails.items]


@router.get("/api/email/search")
async def search_emails_endpoint(
    q: str,
    account_id: str | None = None,
    limit: int = 20,
    user: User | None = Depends(require_auth),
    repo: EmailRepositoryPort = Depends(_email_repository),
) -> list[EmailResponse]:
    """REQ-003 (email-inbox): busca emails do user por subject/body/from.

    Cross-user nunca vaza — `SearchEmails.execute` filtra por `user_id`
    via JOIN `emails → email_accounts → users`, mesma defesa que
    `list_emails_endpoint`. `account_id` opcional restringe a busca a
    uma conta; sem filtro, busca em todas as contas próprias do user.

    Rota vem ANTES de `/api/email/{email_id}` no router — FastAPI casa
    `search` como `email_id` se a rota com path param for declarada
    primeiro.
    """
    if not q.strip():
        raise HTTPException(status_code=422, detail="q cannot be empty")
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if limit > 100:
        limit = 100
    result = await SearchEmails(repository=repo).execute(
        user_id=user.id,
        account_id=account_id,
        query=q,
        limit=limit,
    )
    return [_to_email_response(e) for e in result.items]


@router.get("/api/email/{email_id}")
async def get_email_endpoint(
    email_id: str,
    user: User | None = Depends(require_auth),
    repo: EmailRepositoryPort = Depends(_email_repository),
) -> EmailResponse:
    """REQ-002: returns sanitized body_html/body_text and 404s for email not owned by caller."""
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    email = await GetEmail(repository=repo).execute(user_id=user.id, email_id=email_id)
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")
    return _to_email_response(email)


# ── Email organize endpoint (inbox-3) ───────────────────────────────────────────


class EmailPatchRequest(BaseModel):
    """Corpo de `PATCH /api/email/{id}` — REQ-004.

    Ambos os campos são opcionais; pelo menos um deve ser fornecido
    (validação no endpoint). `folder` deve ser string não-vazia quando
    presente.
    """

    is_read: bool | None = None
    folder: str | None = None


@router.patch("/api/email/{email_id}")
async def patch_email_endpoint(
    email_id: str,
    body: EmailPatchRequest,
    user: User | None = Depends(require_auth),
    repo: EmailRepositoryPort = Depends(_email_repository),
) -> EmailResponse:
    """REQ-004: alterna `is_read` e/ou move `folder`, escopado ao dono.

    Cross-user ou email inexistente retorna 404 — mesma regra de não
    revelar existência aplicada a `GET /api/email/{id}`. Sem campos no
    corpo, 422.
    """
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if body.is_read is None and body.folder is None:
        raise HTTPException(
            status_code=422, detail="At least one of is_read or folder is required"
        )
    if body.folder is not None and not body.folder.strip():
        raise HTTPException(status_code=422, detail="folder cannot be empty")

    if body.folder is not None:
        moved = await repo.move_folder(
            user_id=user.id, email_id=email_id, folder=body.folder
        )
        if not moved:
            raise HTTPException(status_code=404, detail="Email not found")
    if body.is_read is True:
        marked = await repo.mark_read(user_id=user.id, email_id=email_id)
        if not marked:
            raise HTTPException(status_code=404, detail="Email not found")

    email = await repo.get(user_id=user.id, email_id=email_id)
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")
    return _to_email_response(email)


# ── Email send endpoint (send-1) ───────────────────────────────────────────────


@router.post("/api/email/send", status_code=201)
async def send_email_endpoint(
    body: SendEmailRequest,
    user: User | None = Depends(require_auth),
    email_account_repo: EmailAccountRepositoryPort = Depends(_email_account_repository),
    integration_repo: UserIntegrationRepositoryPort = Depends(_user_integration_repository),
    email_repo: EmailRepositoryPort = Depends(_email_repository),
) -> SendEmailResponse:
    """Envia email via SMTP usando as credenciais da conta IMAP do usuário."""
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not body.to_addresses:
        raise HTTPException(status_code=422, detail="to_addresses cannot be empty")

    use_case = SendEmail(
        email_account_repository=email_account_repo,
        integration_repository=integration_repo,
        email_repository=email_repo,
    )
    try:
        result = await use_case.execute(
            user_id=user.id,
            account_id=body.account_id,
            to_addresses=body.to_addresses,
            subject=body.subject,
            body_text=body.body_text,
            body_html=body.body_html,
            cc_addresses=body.cc_addresses,
            bcc_addresses=body.bcc_addresses,
            in_reply_to=body.in_reply_to,
            references=body.references,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SmtpAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SendEmailResponse(
        message_id=result.message_id,
        sent_at=result.sent_at,
        thread_id=result.thread_id,
        subject=body.subject,
    )
