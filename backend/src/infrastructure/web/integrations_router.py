"""Rotas REST de `UserIntegration` e de `POST /api/integrations/telegram/link-code`.

Mesmo molde de `scheduling_router.py`: dependency-factory
`_user_integration_repository()` constrói `PostgresUserIntegrationRepository`
por requisição a partir de `POSTGRES_URI`. `user_id`/`is_admin` são resolvidos
do `User` de `require_auth` — nunca de um campo do corpo da requisição
(REQ-001 do spec `user-integration-credentials-store`). Payloads de escrita
são validados contra o schema Pydantic do `integration_type` (REQ-003) antes
de qualquer chamada de caso de uso — nenhum outro ponto de entrada faz isso,
esta é a fronteira do caso de uso para esse spec. `config` nunca aparece na
listagem para entradas de outro usuário (REQ-004) — `UserIntegrationSummary`
já resolve isso, o router só espelha o campo.

`GET`/`PUT /api/integrations/{id}` devolvem 404 tanto para id inexistente
quanto para entrada de outro usuário — REQ-001 exige não revelar existência.
`DELETE` segue o mesmo princípio via um no-op silencioso de
`DeleteUserIntegration` (sempre 204, com ou sem mudança de estado).

`POST /api/integrations/telegram/link-code` usa seu próprio port
(`TelegramLinkCodeRepositoryPort`) e dependency-factory
(`_telegram_link_code_repository`) — tabela separada de `user_integrations`
(design Decision 3 de `user-integration-credentials`), o código gerado é
sempre atrelado ao `user_id` da sessão (REQ-001 do spec
`user-integration-credentials-telegram-account-linking`).
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError

from src.application.integrations.config_schemas import (
    UnknownIntegrationTypeError,
    validate_config,
)
from src.application.ports.telegram_link_code_repository import (
    TelegramLinkCodeRepositoryPort,
)
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.application.use_cases.create_telegram_link_code import CreateTelegramLinkCode
from src.application.use_cases.delete_user_integration import DeleteUserIntegration
from src.application.use_cases.get_user_integration import (
    GetUserIntegration,
    UserIntegrationAdminDecryptionForbiddenError,
)
from src.application.use_cases.list_user_integrations import ListUserIntegrations
from src.application.use_cases.save_user_integration import SaveUserIntegration
from src.domain.integrations import UserIntegration
from src.domain.shared.errors import DomainError
from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.users import User
from src.infrastructure.persistence.telegram_link_codes_repository import (
    PostgresTelegramLinkCodeRepository,
)
from src.infrastructure.persistence.user_integrations_repository import (
    PostgresUserIntegrationRepository,
)

router = APIRouter()


def _user_integration_repository() -> UserIntegrationRepositoryPort:
    """Constrói o repositório a partir de `POSTGRES_URI`."""
    return PostgresUserIntegrationRepository(os.environ["POSTGRES_URI"])


def _telegram_link_code_repository() -> TelegramLinkCodeRepositoryPort:
    """Constrói o repositório de códigos de vínculo a partir de `POSTGRES_URI`."""
    return PostgresTelegramLinkCodeRepository(os.environ["POSTGRES_URI"])


class UserIntegrationWriteRequest(BaseModel):
    """Corpo de `POST`/`PUT /api/integrations`. Nenhum campo de ownership."""

    integration_type: str
    config: dict[str, object]


class UserIntegrationResponse(BaseModel):
    """Contrato HTTP de uma `UserIntegration` — `config` sempre presente (é o dono)."""

    id: str
    user_id: str
    integration_type: str
    config: dict[str, object]
    created_at: datetime
    updated_at: datetime


class UserIntegrationSummaryResponse(BaseModel):
    """Contrato HTTP de listagem — `config` ausente para entradas de outro usuário (REQ-004)."""

    id: str
    user_id: str
    integration_type: str
    config: dict[str, object] | None
    created_at: datetime
    updated_at: datetime


def _to_response(integration: UserIntegration) -> UserIntegrationResponse:
    return UserIntegrationResponse(
        id=integration.id,
        user_id=integration.user_id,
        integration_type=integration.integration_type,
        config=integration.config,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


def _validate_write_payload(body: UserIntegrationWriteRequest) -> None:
    """REQ-003: valida `config` contra o schema do `integration_type` antes de persistir."""
    try:
        validate_config(body.integration_type, body.config)
    except UnknownIntegrationTypeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/integrations")
async def list_integrations_endpoint(
    user: User | None = Depends(require_auth),
    repo: UserIntegrationRepositoryPort = Depends(_user_integration_repository),
) -> list[UserIntegrationSummaryResponse]:
    """REQ-001/REQ-004: escopado ao dono; admin vê metadados de todos sem config alheio."""
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    use_case = ListUserIntegrations(repository=repo)
    summaries = await use_case.execute(
        caller_user_id=user.id, is_admin=user.role == "admin"
    )
    return [
        UserIntegrationSummaryResponse(
            id=s.id,
            user_id=s.user_id,
            integration_type=s.integration_type,
            config=s.config,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in summaries
    ]


@router.post("/api/integrations", status_code=201)
async def create_integration_endpoint(
    body: UserIntegrationWriteRequest,
    user: User | None = Depends(require_auth),
    repo: UserIntegrationRepositoryPort = Depends(_user_integration_repository),
) -> UserIntegrationResponse:
    """REQ-001: `user_id` sempre resolvido da sessão, nunca do corpo."""
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    _validate_write_payload(body)

    try:
        integration = UserIntegration(
            id=uuid.uuid4().hex,
            user_id=user.id,
            integration_type=body.integration_type,
            config=body.config,
        )
    except DomainError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    use_case = SaveUserIntegration(repository=repo)
    saved = await use_case.execute(
        integration=integration, caller_user_id=user.id, is_admin=user.role == "admin"
    )
    if saved is None:
        raise HTTPException(status_code=403, detail="Forbidden")
    return _to_response(saved)


class TelegramLinkCodeResponse(BaseModel):
    """Contrato HTTP de `POST /api/integrations/telegram/link-code`."""

    code: str
    expires_at: datetime


@router.post("/api/integrations/telegram/link-code", status_code=201)
async def create_telegram_link_code_endpoint(
    user: User | None = Depends(require_auth),
    repo: TelegramLinkCodeRepositoryPort = Depends(_telegram_link_code_repository),
) -> TelegramLinkCodeResponse:
    """REQ-001 (telegram-account-linking): código atrelado ao `user_id` da sessão."""
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    use_case = CreateTelegramLinkCode(repository=repo)
    link_code = await use_case.execute(caller_user_id=user.id)
    return TelegramLinkCodeResponse(code=link_code.code, expires_at=link_code.expires_at)


@router.get("/api/integrations/{integration_id}")
async def get_integration_endpoint(
    integration_id: str,
    user: User | None = Depends(require_auth),
    repo: UserIntegrationRepositoryPort = Depends(_user_integration_repository),
) -> UserIntegrationResponse:
    """REQ-001: não-dono não-admin recebe 404 (não revela existência); REQ-004: admin não-dono recebe 403."""
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    use_case = GetUserIntegration(repository=repo)
    try:
        integration = await use_case.execute(
            integration_id=integration_id,
            caller_user_id=user.id,
            is_admin=user.role == "admin",
        )
    except UserIntegrationAdminDecryptionForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if integration is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    return _to_response(integration)


@router.put("/api/integrations/{integration_id}")
async def update_integration_endpoint(
    integration_id: str,
    body: UserIntegrationWriteRequest,
    user: User | None = Depends(require_auth),
    repo: UserIntegrationRepositoryPort = Depends(_user_integration_repository),
) -> UserIntegrationResponse:
    """REQ-001: dono/admin atualiza; não-dono não-admin recebe 404 (sem revelar existência)."""
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    existing = await repo.get(integration_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Integration not found")

    _validate_write_payload(body)

    try:
        integration = UserIntegration(
            id=integration_id,
            user_id=existing.user_id,
            integration_type=body.integration_type,
            config=body.config,
            created_at=existing.created_at,
        )
    except DomainError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    use_case = SaveUserIntegration(repository=repo)
    saved = await use_case.execute(
        integration=integration, caller_user_id=user.id, is_admin=user.role == "admin"
    )
    if saved is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    return _to_response(saved)


@router.delete("/api/integrations/{integration_id}", status_code=204)
async def delete_integration_endpoint(
    integration_id: str,
    user: User | None = Depends(require_auth),
    repo: UserIntegrationRepositoryPort = Depends(_user_integration_repository),
) -> None:
    """REQ-001: dono/admin remove; não-dono não-admin: no-op silencioso (mesma resposta)."""
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    use_case = DeleteUserIntegration(repository=repo)
    await use_case.execute(
        integration_id=integration_id,
        caller_user_id=user.id,
        is_admin=user.role == "admin",
    )
