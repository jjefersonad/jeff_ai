"""Registro de schema Pydantic por `integration_type`.

Fronteira do caso de uso (design Decision 1 de `user-integration-credentials`):
um `config` payload é validado aqui, contra o schema do seu `integration_type`,
antes de qualquer cifra ou persistência (REQ-003 do spec
`user-integration-credentials-store`). Adicionar um `integration_type` novo é
uma chamada a `register_integration_type` — nunca uma migração da tabela
`user_integrations`.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class TelegramIntegrationConfig(BaseModel):
    """`config` de um vínculo Telegram: o `chat_id` autorizado."""

    chat_id: str


class WhatsAppBusinessIntegrationConfig(BaseModel):
    """`config` de um vínculo WhatsApp Business: o `phone_number` autorizado."""

    phone_number: str = Field(min_length=1)


class SmtpIntegrationConfig(BaseModel):
    """Stub — adapter de SMTP está fora de escopo desta mudança."""


class UnknownIntegrationTypeError(ValueError):
    """`integration_type` sem schema registrado em `validate_config`."""


_REGISTRY: dict[str, type[BaseModel]] = {
    "telegram": TelegramIntegrationConfig,
    "whatsapp_business": WhatsAppBusinessIntegrationConfig,
    "smtp": SmtpIntegrationConfig,
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
