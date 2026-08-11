"""Testes do cliente SMTP (`src/infrastructure/email/smtp_client.py`).

Cobre a regressão de produção: `aiosmtplib.SMTP.login()` levanta
`aiosmtplib.SMTPAuthenticationError` — uma classe distinta da `smtplib`
(stdlib) do mesmo nome. Um `except smtplib.SMTPAuthenticationError` nunca
captura a exceção real do `aiosmtplib`, então ela escapava sem tratamento,
derrubando a resposta ASGI a meio (sem corpo JSON) e fazendo o frontend cair
no fallback genérico "Falha inesperada" em vez do erro estruturado que
`email_router.py` monta a partir de `SmtpAuthError`.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from aiosmtplib import SMTPAuthenticationError

from src.application.integrations.config_schemas import ImapIntegrationConfig
from src.infrastructure.email.smtp_client import SmtpAuthError, send_email_via_smtp


def _config() -> ImapIntegrationConfig:
    return ImapIntegrationConfig(
        imap_host="imap.example.com",
        imap_port=993,
        imap_username="user@example.com",
        imap_password="wrong-password",
        smtp_host="smtp.example.com",
        smtp_port=587,
    )


@pytest.mark.asyncio
async def test_send_email_via_smtp_wraps_aiosmtplib_auth_error() -> None:
    """unit: a `aiosmtplib.SMTPAuthenticationError` real do login vira `SmtpAuthError`."""
    with (
        patch("src.infrastructure.email.smtp_client.SMTP.connect", new=AsyncMock()),
        patch(
            "src.infrastructure.email.smtp_client.SMTP.login",
            new=AsyncMock(side_effect=SMTPAuthenticationError(535, "Authentication Failed")),
        ),
        patch("src.infrastructure.email.smtp_client.SMTP.quit", new=AsyncMock()),
    ):
        with pytest.raises(SmtpAuthError):
            await send_email_via_smtp(
                config=_config(),
                from_name="User",
                to_addresses=["dest@example.com"],
                cc_addresses=[],
                bcc_addresses=[],
                subject="Assunto",
                body_text="Corpo",
                body_html=None,
                in_reply_to=None,
                references=None,
                attachments=None,
            )
