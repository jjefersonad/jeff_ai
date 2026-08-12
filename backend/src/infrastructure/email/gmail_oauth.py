"""Cliente OAuth2 do Google para conectar contas Gmail (gmail-account-oauth-connection).

`build_authorize_url` monta a URL de consentimento do Google (REQ-001 do
spec `gmail-oauth-connection`) a partir de `GOOGLE_OAUTH_CLIENT_ID`/
`GOOGLE_OAUTH_REDIRECT_URI`. A troca de `code` por tokens e o refresh
chegam nas próximas tasks (`task-oauth-2`/`task-oauth-3`).
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from src.application.integrations.config_schemas import (
    GmailIntegrationConfig,
    validate_config,
)
from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.domain.integrations import UserIntegration

_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"

# `https://mail.google.com/` autoriza XOAUTH2 contra imap.gmail.com/
# smtp.gmail.com (design Decision 1); `userinfo.email`/`openid` resolvem o
# endereço Gmail conectado, necessário para o dedupe de REQ-005.
_SCOPES = " ".join(
    [
        "https://mail.google.com/",
        "https://www.googleapis.com/auth/userinfo.email",
        "openid",
    ]
)


class MissingGoogleOAuthConfigError(RuntimeError):
    """Uma env var `GOOGLE_OAUTH_*` obrigatória está ausente ou vazia."""


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise MissingGoogleOAuthConfigError(
            f"{name} não configurada. Defina-a no `.env` (ver `.env.example`)."
        )
    return value


def build_authorize_url(state: str) -> str:
    """Monta a URL de consentimento OAuth2 do Google para conectar uma conta Gmail.

    Raises:
        MissingGoogleOAuthConfigError: `GOOGLE_OAUTH_CLIENT_ID` ou
            `GOOGLE_OAUTH_REDIRECT_URI` ausente/vazia no ambiente.
    """
    client_id = _required_env("GOOGLE_OAUTH_CLIENT_ID")
    redirect_uri = _required_env("GOOGLE_OAUTH_REDIRECT_URI")

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": _SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{_AUTHORIZE_URL}?{urlencode(params)}"


class MissingRefreshTokenError(RuntimeError):
    """Google respondeu sem `refresh_token` — provável consentimento já concedido antes."""


@dataclass(frozen=True)
class GoogleTokenResult:
    """Resultado da troca de `code` por tokens (`exchange_code_for_tokens`)."""

    access_token: str
    refresh_token: str
    expires_in: int
    email_address: str


async def _post_token_request(data: dict[str, str]) -> httpx.Response:
    """POST compartilhado ao endpoint de token do Google, sem levantar em HTTP 4xx/5xx.

    Cada chamador decide como reagir ao status (`response.raise_for_status()`
    ou uma checagem mais específica, como `refresh_access_token` faz para
    distinguir `invalid_grant` de qualquer outra falha).
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        return await client.post(_TOKEN_URL, data=data)


def _decode_id_token_email(id_token: str) -> str:
    """Extrai `email` do payload de um `id_token` JWT, sem verificar assinatura.

    Seguro aqui porque `id_token` veio direto do endpoint de token do
    Google sobre TLS (nunca de um cliente não confiável), então não há
    superfície de falsificação a defender.
    """
    _, payload_b64, _ = id_token.split(".")
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded))
    return payload["email"]


async def exchange_code_for_tokens(code: str) -> GoogleTokenResult:
    """Troca um `code` de autorização pelos tokens Gmail e o endereço conectado.

    Raises:
        MissingGoogleOAuthConfigError: config `GOOGLE_OAUTH_*` ausente.
        MissingRefreshTokenError: resposta do Google sem `refresh_token`.
        httpx.HTTPError: falha de rede/HTTP na chamada ao endpoint de token.
    """
    client_id = _required_env("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = _required_env("GOOGLE_OAUTH_CLIENT_SECRET")
    redirect_uri = _required_env("GOOGLE_OAUTH_REDIRECT_URI")

    response = await _post_token_request(
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    )
    response.raise_for_status()
    payload = response.json()

    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        raise MissingRefreshTokenError(
            "Google não retornou refresh_token — provável consentimento já "
            "concedido antes sem `prompt=consent`. Revogue o acesso em "
            "myaccount.google.com/permissions e tente novamente."
        )

    return GoogleTokenResult(
        access_token=payload["access_token"],
        refresh_token=refresh_token,
        expires_in=payload["expires_in"],
        email_address=_decode_id_token_email(payload["id_token"]),
    )


class RefreshTokenRevokedError(RuntimeError):
    """O `refresh_token` foi revogado/rejeitado pelo Google (400 `invalid_grant`)."""


@dataclass(frozen=True)
class RefreshedToken:
    """Resultado de `refresh_access_token` — novo `access_token` + sua expiração."""

    access_token: str
    expiry: datetime


async def refresh_access_token(refresh_token: str) -> RefreshedToken:
    """Obtém um novo `access_token` a partir de um `refresh_token` válido.

    Raises:
        MissingGoogleOAuthConfigError: config `GOOGLE_OAUTH_*` ausente.
        RefreshTokenRevokedError: Google rejeitou o refresh_token (400 `invalid_grant`).
        httpx.HTTPError: qualquer outra falha de rede/HTTP.
    """
    client_id = _required_env("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = _required_env("GOOGLE_OAUTH_CLIENT_SECRET")

    response = await _post_token_request(
        {
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
        }
    )
    if response.status_code == 400 and response.json().get("error") == "invalid_grant":
        raise RefreshTokenRevokedError(
            "Google rejeitou o refresh_token (invalid_grant) — provavelmente "
            "revogado pelo usuário. A conta precisa ser reconectada."
        )
    response.raise_for_status()
    payload = response.json()

    expiry = datetime.now(UTC) + timedelta(seconds=payload["expires_in"])
    return RefreshedToken(access_token=payload["access_token"], expiry=expiry)


async def ensure_fresh_token(
    integration: UserIntegration,
    integration_repository: UserIntegrationRepositoryPort,
) -> GmailIntegrationConfig:
    """Garante um `access_token` Gmail válido, refrescando e persistindo se preciso.

    Recebe o `UserIntegration` inteiro, não só o `config` decodificado —
    persistir o token refrescado via `integration_repository.save(...)`
    exige `id`/`user_id`, que um `GmailIntegrationConfig` isolado não carrega.

    Raises:
        RefreshTokenRevokedError: propagada de `refresh_access_token` sem
            ser engolida, para o caller (sync worker / `SendEmail`) marcar a
            conta `status="error"`.
    """
    config = validate_config("gmail", integration.config)
    assert isinstance(config, GmailIntegrationConfig)

    if config.token_expiry > datetime.now(UTC):
        return config

    refreshed = await refresh_access_token(config.refresh_token)
    new_config = config.model_copy(
        update={"access_token": refreshed.access_token, "token_expiry": refreshed.expiry}
    )
    await integration_repository.save(
        UserIntegration(
            id=integration.id,
            user_id=integration.user_id,
            integration_type=integration.integration_type,
            config=new_config.model_dump(mode="json"),
            created_at=integration.created_at,
        )
    )
    return new_config
