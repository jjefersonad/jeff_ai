"""Testes de `src/application/use_cases/start_gmail_oauth.py`.

Cobre a task `gmail-account-oauth-connection-task-accounts-1`: `StartGmailOAuth`
delega a construção da URL de consentimento a `build_authorize_url` injetado
(REQ-001 do spec `gmail-oauth-connection`).
"""
from __future__ import annotations

from src.application.use_cases.start_gmail_oauth import StartGmailOAuth


def _fake_build_authorize_url(state: str) -> str:
    return f"https://accounts.google.com/o/oauth2/v2/auth?state={state}"


def test_start_gmail_oauth_returns_build_authorize_url_result() -> None:
    """gmail-account-oauth-connection-task-accounts-1-unit-1 (REQ-001)."""
    use_case = StartGmailOAuth(build_authorize_url=_fake_build_authorize_url)

    result = use_case.execute("abc123")

    assert result == "https://accounts.google.com/o/oauth2/v2/auth?state=abc123"
