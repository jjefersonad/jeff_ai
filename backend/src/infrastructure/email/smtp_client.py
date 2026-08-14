"""Cliente SMTP: envio de email com suporte a to/cc/bcc, anexos e threading.

`resolve_bodies`/`_build_mime` (email-send-html-only-by-default-task-smtp-1,
REQ-009) decidem o formato MIME de cada envio conforme o par
`(body_text, body_html)` recebido do caller:

- `text-only`  → single-part `text/html` gerado a partir do plain
                 (`<p>...escaped...</p>`, sanitizado por `sanitize_body_html`)
- `html-only`  → single-part `text/html` (sem `text/plain` duplicado)
- `both`       → `multipart/alternative` com `text/plain` primeiro e
                 `text/html` segundo, em HTML sanitizado

`sanitize_body_html` (mesma função do `imap_client`, allowlist REQ-018)
garante que um `<script>` ou `onerror=` injetado pelo caller não alcance
o recipient, e que apresentação HTML de e-mail sobreviva no wire.

`send_email_via_smtp` aceita `body_text: str | None = None` (antes era
obrigatório) e usa os helpers acima para montar o payload.
"""
from __future__ import annotations

import email.encoders
import email.mime.base
import email.mime.multipart
import email.mime.text
import html
from email.header import Header
from email.utils import formataddr, make_msgid

from aiosmtplib import SMTP, SMTPAuthenticationError

from src.application.integrations.config_schemas import (
    GmailIntegrationConfig,
    ImapIntegrationConfig,
)
from src.infrastructure.email.imap_client import sanitize_body_html


class SmtpAuthError(Exception):
    """Servidor SMTP recusou a autenticação."""


async def _authenticate(smtp: SMTP, config: ImapIntegrationConfig | GmailIntegrationConfig) -> None:
    """Autentica `smtp` — XOAUTH2 para contas Gmail, LOGIN para as demais.

    Gmail não tem `smtp_password`/`imap_password` (não existe senha — só
    `access_token`), então o branch por tipo evita acessar um atributo que
    `GmailIntegrationConfig` não tem (design Decision 1 de
    `gmail-account-oauth-connection`).
    """
    smtp_user = config.smtp_username or config.imap_username
    if isinstance(config, GmailIntegrationConfig):
        await smtp.auth_xoauth2(smtp_user, config.access_token)
    else:
        smtp_password = config.smtp_password or config.imap_password
        await smtp.login(smtp_user, smtp_password)


def _has_value(value: str | None) -> bool:
    """True se `value` é uma string não-vazia (após strip)."""
    return isinstance(value, str) and bool(value.strip())


def resolve_bodies(
    body_text: str | None, body_html: str | None
) -> tuple[str | None, str | None]:
    """Resolve o par `(body_text, body_html)` que vai pro wire e pro Sent row.

    Returns:
        Tupla `(resolved_text, resolved_html)` onde:
        - Se só `body_html` foi fornecido → `(None, sanitized_html)`.
        - Se só `body_text` foi fornecido → `(text, "<p>escaped</p>")` sanitizado.
        - Se ambos foram fornecidos → `(text, sanitized_html)`.

    Raises:
        ValueError: ambos `body_text` e `body_html` ausentes ou vazios
            (mensagem `"Send body required"`). Mesma regra do HTTP
            route 422 (REQ-010 scenario 2).
    """
    has_text = _has_value(body_text)
    has_html = _has_value(body_html)

    if not has_text and not has_html:
        raise ValueError("Send body required")

    if has_html:
        resolved_html = sanitize_body_html(body_html or "")
    else:
        assert body_text is not None
        escaped = html.escape(body_text)
        resolved_html = sanitize_body_html(f"<p>{escaped}</p>")

    resolved_text: str | None = body_text if has_text else None
    return resolved_text, resolved_html


def _build_mime(body_text: str | None, body_html: str | None):
    """Monta o payload MIME do email conforme o par resolvido.

    - `text-only`  → `MIMEText(generated_html, "html", "utf-8")`
    - `html-only`  → `MIMEText(body_html, "html", "utf-8")`
    - `both`       → `MIMEMultipart("alternative")` com plain primeiro,
                     html segundo
    """
    has_text = _has_value(body_text)
    has_html = _has_value(body_html)
    assert has_text or has_html, "resolve_bodies deve ter garantido ao menos um"

    if has_text and has_html:
        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg.attach(email.mime.text.MIMEText(body_text, "plain", "utf-8"))
        msg.attach(email.mime.text.MIMEText(sanitize_body_html(body_html or ""), "html", "utf-8"))
        return msg

    # html-only ou text-only: usa resolve_bodies para reaplicar a regra
    # "text-only → HTML gerado" e a sanitização numa única fonte de verdade.
    _, resolved_html = resolve_bodies(body_text, body_html)
    return email.mime.text.MIMEText(resolved_html, "html", "utf-8")


async def send_email_via_smtp(
    config: ImapIntegrationConfig | GmailIntegrationConfig,
    from_name: str,
    to_addresses: list[str],
    cc_addresses: list[str],
    bcc_addresses: list[str],
    subject: str,
    body_text: str | None = None,
    body_html: str | None = None,
    in_reply_to: str | None = None,
    references: str | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,  # [(filename, data, mime_type), ...]
) -> str:
    """Envia email via SMTP da conta configurada.

    Returns the Message-ID of the sent message.

    Raises:
        ValueError: `body_text` e `body_html` ambos ausentes/vazios.
        SmtpAuthError: autenticação recusada.
        Exception: falhas de rede/timeout propagam sem embrulho.
    """
    # Resolve o par de bodies (gera HTML a partir de plain-only; sanitiza).
    resolved_text, resolved_html = resolve_bodies(body_text, body_html)

    # Build the email message — outer container é sempre `multipart/mixed`
    # para acomodar attachments, mas o `payload` (corpo) é decidido por
    # `_build_mime` conforme o par resolvido.
    msg = email.mime.multipart.MIMEMultipart("mixed")
    msg["From"] = formataddr((from_name, config.smtp_username or config.imap_username))
    msg["To"] = ", ".join(to_addresses)
    if cc_addresses:
        msg["Cc"] = ", ".join(cc_addresses)
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    msg["Subject"] = Header(subject, "utf-8").encode()
    msg["Date"] = email.utils.formatdate(localtime=True)
    # Message-ID is required by RFC 5322 §3.6.4 and expected by every
    # well-behaved SMTP server. `email.mime.multipart.MIMEMultipart` does
    # NOT auto-generate one — without this header the SMTP send returns
    # msg["Message-ID"] == None and the FastAPI response model (declared
    # `message_id: str`, not Optional) rejects it with a Pydantic
    # `string_type` validation error. We anchor the right-hand side of
    # the @ to the sender's domain so remote MTAs accept it.
    sender = config.smtp_username or config.imap_username
    sender_domain = sender.split("@", 1)[1] if "@" in sender else "localhost"
    msg["Message-ID"] = make_msgid(domain=sender_domain)

    # Body — uma única parte (single-part HTML) ou `multipart/alternative`
    # (plain+html). Anexos continuam como parts adicionais do `mixed`.
    msg.attach(_build_mime(resolved_text, resolved_html))

    # Attachments
    if attachments:
        for filename, data, mime_type in attachments:
            part = email.mime.base.MIMEBase(
                mime_type.split("/")[0], mime_type.split("/")[1].replace("+xml", "+xml")
            )
            part.set_payload(data)
            email.encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename*=UTF-8''{filename}")
            msg.attach(part)

    # Determine recipients (all non-empty lists)
    all_recipients = list(to_addresses)
    if cc_addresses:
        all_recipients.extend(cc_addresses)
    if bcc_addresses:
        all_recipients.extend(bcc_addresses)

    # Send
    smtp_host = config.smtp_host or config.imap_host
    smtp_port = config.smtp_port or 587
    smtp_user = config.smtp_username or config.imap_username

    smtp = SMTP(hostname=smtp_host, port=smtp_port)
    await smtp.connect()
    try:
        await _authenticate(smtp, config)
        await smtp.send_message(msg, sender=smtp_user, recipients=all_recipients)
    except SMTPAuthenticationError as exc:
        raise SmtpAuthError(f"SMTP authentication failed: {exc}") from exc
    finally:
        await smtp.quit()

    # Return Message-ID from the sent message
    return msg["Message-ID"]
