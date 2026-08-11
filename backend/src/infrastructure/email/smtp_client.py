"""Cliente SMTP: envio de email com suporte a to/cc/bcc, anexos e threading."""
from __future__ import annotations

import email.encoders
import email.mime.base
import email.mime.multipart
import email.mime.text
from email.header import Header
from email.utils import formataddr, make_msgid

from aiosmtplib import SMTP, SMTPAuthenticationError

from src.application.integrations.config_schemas import ImapIntegrationConfig


class SmtpAuthError(Exception):
    """Servidor SMTP recusou a autenticação."""


async def send_email_via_smtp(
    config: ImapIntegrationConfig,
    from_name: str,
    to_addresses: list[str],
    cc_addresses: list[str],
    bcc_addresses: list[str],
    subject: str,
    body_text: str,
    body_html: str | None,
    in_reply_to: str | None,
    references: str | None,
    attachments: list[tuple[str, bytes, str]] | None,  # [(filename, data, mime_type), ...]
) -> str:
    """Envia email via SMTP da conta configurada.

    Returns the Message-ID of the sent message.

    Raises:
        SmtpAuthError: autenticação recusada.
        Exception: falhas de rede/timeout propagam sem embrulho.
    """
    # Build the email message
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

    # Body
    if body_html:
        msg.attach(email.mime.text.MIMEText(body_html, "html", "utf-8"))
    msg.attach(email.mime.text.MIMEText(body_text, "plain", "utf-8"))

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
    smtp_password = config.smtp_password or config.imap_password

    smtp = SMTP(hostname=smtp_host, port=smtp_port)
    await smtp.connect()
    try:
        await smtp.login(smtp_user, smtp_password)
        await smtp.send_message(msg, sender=smtp_user, recipients=all_recipients)
    except SMTPAuthenticationError as exc:
        raise SmtpAuthError(f"SMTP authentication failed: {exc}") from exc
    finally:
        await smtp.quit()

    # Return Message-ID from the sent message
    return msg["Message-ID"]
