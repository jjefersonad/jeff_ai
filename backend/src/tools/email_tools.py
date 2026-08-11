"""Email tools for the agent — thin wrappers over use cases scoped to the session user.

Ownership comes exclusively from `resolve_user_id()` (session context).
Tools that accept `user_id` as a parameter IGNORE it (same pattern as CRM tools).
"""
from __future__ import annotations

import os
from typing import Any

from langchain_core.tools import tool

from src.application.use_cases.get_email import GetEmail
from src.application.use_cases.list_email_accounts import ListEmailAccounts
from src.application.use_cases.list_emails import ListEmails
from src.application.use_cases.search_emails import SearchEmails
from src.application.use_cases.send_email import SendEmail
from src.domain.email.models import EmailAccountStatus
from src.infrastructure.ownership.store import resolve_user_id
from src.infrastructure.persistence.email_account_repository import (
    PostgresEmailAccountRepository,
)
from src.infrastructure.persistence.email_repository import PostgresEmailRepository
from src.infrastructure.persistence.user_integrations_repository import (
    PostgresUserIntegrationRepository,
)

_NOE_IDENTITY = (
    "Identidade do usuário não resolvida para esta sessão; "
    "não é possível acessar o email."
)


# --------------------------------------------------------------------------- #
# Repositories (same pattern as crm_tools.py — built directly, not injected)
# --------------------------------------------------------------------------- #


def _email_repository():
    return PostgresEmailRepository(os.environ["POSTGRES_URI"])


def _email_account_repository():
    return PostgresEmailAccountRepository(os.environ["POSTGRES_URI"])


def _integration_repository():
    return PostgresUserIntegrationRepository(os.environ["POSTGRES_URI"])


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


async def _require_user_id() -> str | dict[str, str]:
    """Resolve user_id from session or return error dict."""
    user_id = await resolve_user_id()
    if not user_id:
        return {"error": _NOE_IDENTITY}
    return user_id


def _email_dict(email) -> dict[str, Any]:
    """Serialize an Email domain object to a dict for tool responses."""
    return {
        "id": email.id,
        "email_account_id": email.email_account_id,
        "message_id": email.message_id,
        "thread_id": email.thread_id,
        "folder": email.folder,
        "from_address": email.from_address,
        "from_name": email.from_name,
        "to_addresses": email.to_addresses,
        "cc_addresses": email.cc_addresses,
        "bcc_addresses": email.bcc_addresses,
        "subject": email.subject,
        "body_text": email.body_text,
        "body_html": email.body_html,
        "is_read": email.is_read,
        "is_starred": email.is_starred,
        "has_attachments": email.has_attachments,
        "contact_id": email.contact_id,
        "received_at": email.received_at.isoformat() if email.received_at else None,
        "created_at": email.created_at.isoformat(),
    }


def _email_account_dict(account) -> dict[str, Any]:
    """Serialize an EmailAccount domain object to a dict."""
    status = account.status
    if isinstance(status, EmailAccountStatus):
        status = status.value
    return {
        "id": account.id,
        "display_name": account.display_name,
        "provider": account.provider,
        "status": status,
        "is_active": account.is_active,
        "last_synced_at": (
            account.last_synced_at.isoformat() if account.last_synced_at else None
        ),
    }


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #


@tool
async def list_emails(
    account_id: str | None = None,
    folder: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """List emails across the user's own connected accounts, ordered by `received_at` DESC.

    Sem `account_id`/`folder`, devolve o inbox unificado de todas as contas
    próprias do usuário resolvido pela sessão (REQ-001 cenário unificado).

    Args:
        account_id: UUID opcional da conta para filtrar; sem filtro = todas as contas do user.
        folder: Nome da pasta (ex.: `INBOX`, `Sent`); sem filtro = todas as pastas.
        limit: Máximo de emails (default: 20, máx: 100).
        offset: Emails a pular (default: 0).
    """
    resolved = await _require_user_id()
    if isinstance(resolved, dict):
        return resolved

    use_case = ListEmails(repository=_email_repository())
    result = await use_case.execute(
        user_id=resolved,
        account_id=account_id,
        folder=folder,
        limit=limit,
        offset=offset,
    )
    return {
        "emails": [_email_dict(e) for e in result.items],
        "count": len(result.items),
        "account_id": result.account_id,
        "folder": result.folder,
    }


@tool
async def read_email(email_id: str) -> dict[str, Any]:
    """Read a single email by ID, including full body content.

    Args:
        email_id: UUID of the email to read.
    """
    resolved = await _require_user_id()
    if isinstance(resolved, dict):
        return resolved

    use_case = GetEmail(repository=_email_repository())
    email = await use_case.execute(user_id=resolved, email_id=email_id)
    if email is None:
        return {"error": "Email not found or access denied"}
    return _email_dict(email)


@tool
async def search_emails(
    query: str,
    account_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search emails by subject, body, or sender.

    Args:
        query: Search term matched case-insensitively against subject,
            body text, and the from address.
        account_id: Optional UUID of account to search within.
        limit: Maximum results (default: 20, max: 100).
    """
    resolved = await _require_user_id()
    if isinstance(resolved, dict):
        return resolved

    use_case = SearchEmails(repository=_email_repository())
    result = await use_case.execute(
        user_id=resolved,
        query=query,
        account_id=account_id,
        limit=limit,
    )
    return {
        "emails": [_email_dict(e) for e in result.items],
        "count": len(result.items),
        "query": result.query,
        "account_id": result.account_id,
    }


@tool
async def get_email_accounts() -> dict[str, Any]:
    """List all email accounts connected to the current user."""
    resolved = await _require_user_id()
    if isinstance(resolved, dict):
        return resolved

    use_case = ListEmailAccounts(repository=_email_account_repository())
    accounts = await use_case.execute(user_id=resolved)
    return {
        "accounts": [_email_account_dict(a) for a in accounts],
        "count": len(accounts),
    }


@tool
async def send_email(
    account_id: str,
    to_addresses: list[str],
    subject: str,
    body_text: str,
    body_html: str | None = None,
    cc_addresses: list[str] | None = None,
    bcc_addresses: list[str] | None = None,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> dict[str, Any]:
    """Send an email via one of the user's connected accounts.

    Requires approval (Tier 3) — previews as a diff before sending.

    Args:
        account_id: UUID of the email account to send from.
        to_addresses: List of recipient email addresses.
        subject: Email subject line.
        body_text: Plain text body.
        body_html: Optional HTML body.
        cc_addresses: Optional CC recipients.
        bcc_addresses: Optional BCC recipients.
        in_reply_to: UUID of the email being replied to. When set, the
            use case propagates the original email's `thread_id` and
            prefixes the subject with `Re:` (idempotent — not double-prefixed).
        references: References header for threading.
    """
    resolved = await _require_user_id()
    if isinstance(resolved, dict):
        return resolved

    use_case = SendEmail(
        email_account_repository=_email_account_repository(),
        integration_repository=_integration_repository(),
        email_repository=_email_repository(),
    )
    try:
        result = await use_case.execute(
            user_id=resolved,
            account_id=account_id,
            to_addresses=to_addresses,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            cc_addresses=cc_addresses,
            bcc_addresses=bcc_addresses,
            in_reply_to=in_reply_to,
            references=references,
        )
        return {
            "message_id": result.message_id,
            "sent_at": result.sent_at.isoformat(),
            "thread_id": result.thread_id,
        }
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Failed to send email: {exc}"}
