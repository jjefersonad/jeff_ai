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

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from aiosmtplib import SMTPAuthenticationError

from src.application.integrations.config_schemas import (
    GmailIntegrationConfig,
    ImapIntegrationConfig,
)
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


def _gmail_config() -> GmailIntegrationConfig:
    return GmailIntegrationConfig(
        email_address="user@gmail.com",
        access_token="ya29.access",
        refresh_token="1//refresh",
        token_expiry=datetime.now(UTC),
    )


async def _send(config: ImapIntegrationConfig | GmailIntegrationConfig) -> str:
    return await send_email_via_smtp(
        config=config,
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
            await _send(_config())


@pytest.mark.asyncio
async def test_send_email_via_smtp_with_gmail_config_uses_auth_xoauth2() -> None:
    """gmail-account-oauth-connection-task-sync-2-unit-1 (REQ-003)."""
    with (
        patch("src.infrastructure.email.smtp_client.SMTP.connect", new=AsyncMock()),
        patch(
            "src.infrastructure.email.smtp_client.SMTP.auth_xoauth2", new=AsyncMock()
        ) as mock_xoauth2,
        patch(
            "src.infrastructure.email.smtp_client.SMTP.login", new=AsyncMock()
        ) as mock_login,
        patch("src.infrastructure.email.smtp_client.SMTP.send_message", new=AsyncMock()),
        patch("src.infrastructure.email.smtp_client.SMTP.quit", new=AsyncMock()),
    ):
        await _send(_gmail_config())

    mock_xoauth2.assert_awaited_once_with("user@gmail.com", "ya29.access")
    mock_login.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_email_via_smtp_with_imap_config_still_uses_login() -> None:
    """gmail-account-oauth-connection-task-sync-2-unit-2 (REQ-003) — regressão."""
    with (
        patch("src.infrastructure.email.smtp_client.SMTP.connect", new=AsyncMock()),
        patch(
            "src.infrastructure.email.smtp_client.SMTP.login", new=AsyncMock()
        ) as mock_login,
        patch("src.infrastructure.email.smtp_client.SMTP.send_message", new=AsyncMock()),
        patch("src.infrastructure.email.smtp_client.SMTP.quit", new=AsyncMock()),
    ):
        await _send(_config())

    mock_login.assert_awaited_once_with("user@example.com", "wrong-password")
