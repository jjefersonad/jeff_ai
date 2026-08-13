"""Registro de schema Pydantic por `integration_type`.

Fronteira do caso de uso (design Decision 1 de `user-integration-credentials`):
um `config` payload é validado aqui, contra o schema do seu `integration_type`,
antes de qualquer cifra ou persistência (REQ-003 do spec
`user-integration-credentials-store`). Adicionar um `integration_type` novo é
uma chamada a `register_integration_type` — nunca uma migração da tabela
`user_integrations`.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TelegramIntegrationConfig(BaseModel):
    """`config` de um vínculo Telegram: o `chat_id` autorizado."""

    chat_id: str


class WhatsAppBusinessIntegrationConfig(BaseModel):
    """`config` de um vínculo WhatsApp Business: o `phone_number` autorizado."""

    phone_number: str = Field(min_length=1)


class SmtpIntegrationConfig(BaseModel):
    """Stub — adapter de SMTP está fora de escopo desta mudança."""


class ImapIntegrationConfig(BaseModel):
    """`config` de uma conta de email genérica IMAP/SMTP (email-client-imap-mvp).

    `smtp_username`/`smtp_password` herdam `imap_username`/`imap_password`
    quando omitidos, já que a maioria dos provedores usa a mesma credencial
    para os dois protocolos.
    """

    imap_host: str = Field(min_length=1)
    imap_port: int
    imap_username: str = Field(min_length=1)
    imap_password: str = Field(min_length=1)
    smtp_host: str = Field(min_length=1)
    smtp_port: int
    smtp_username: str | None = Field(default=None, min_length=1)
    smtp_password: str | None = Field(default=None, min_length=1)

    def model_post_init(self, __context: object) -> None:
        """Fill `smtp_username`/`smtp_password` from the IMAP credentials when omitted."""
        if self.smtp_username is None:
            self.smtp_username = self.imap_username
        if self.smtp_password is None:
            self.smtp_password = self.imap_password


class GmailIntegrationConfig(BaseModel):
    """`config` de uma conta Gmail conectada via OAuth2 (gmail-account-oauth-connection).

    Ao contrário de `ImapIntegrationConfig`, não há usuário/senha: os
    segredos são `access_token`/`refresh_token`/`token_expiry` obtidos pelo
    fluxo OAuth (design Decision 1). Host/porta IMAP/SMTP são fixos ao Gmail
    — expostos como `@property`, nunca como `Field`, para que nenhum valor
    de payload possa sobrescrevê-los.
    """

    email_address: str = Field(min_length=1)
    access_token: str = Field(min_length=1)
    refresh_token: str = Field(min_length=1)
    token_expiry: datetime

    @property
    def imap_host(self) -> str:
        return "imap.gmail.com"

    @property
    def imap_port(self) -> int:
        return 993

    @property
    def imap_username(self) -> str:
        return self.email_address

    @property
    def smtp_host(self) -> str:
        return "smtp.gmail.com"

    @property
    def smtp_port(self) -> int:
        return 587

    @property
    def smtp_username(self) -> str:
        return self.email_address


class UnknownIntegrationTypeError(ValueError):
    """`integration_type` sem schema registrado em `validate_config`."""


_REGISTRY: dict[str, type[BaseModel]] = {
    "telegram": TelegramIntegrationConfig,
    "whatsapp_business": WhatsAppBusinessIntegrationConfig,
    "smtp": SmtpIntegrationConfig,
    "imap": ImapIntegrationConfig,
    "gmail": GmailIntegrationConfig,
}


def register_integration_type(integration_type: str, schema: type[BaseModel]) -> None:
    """Registra `schema` para `integration_type`, disponível de imediato em `validate_config`."""
    _REGISTRY[integration_type] = schema


def validate_config(integration_type: str, payload: dict[str, object]) -> BaseModel:
    """Valida `payload` contra o schema registrado para `integration_type`.

    Levanta `UnknownIntegrationTypeError` se o tipo não tiver schema
    registrado, ou `pydantic.ValidationError` se o payload não bater com o
    schema.
    """
    try:
        schema = _REGISTRY[integration_type]
    except KeyError as exc:
        raise UnknownIntegrationTypeError(
            f"integration_type sem schema registrado: {integration_type!r}"
        ) from exc
    return schema.model_validate(payload)
