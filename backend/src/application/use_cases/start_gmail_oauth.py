"""Caso de uso: iniciar o fluxo OAuth2 do Google para conectar uma conta Gmail.

REQ-001 do spec `gmail-oauth-connection`. `build_authorize_url` é injetado —
não importado direto de `infrastructure/` — para manter a Dependency Rule,
mesmo padrão de `VerifyLogin` em `connect_email_account.py`.
`src/infrastructure/web/email_router.py` injeta a implementação real
(`gmail_oauth.build_authorize_url`).
"""
from __future__ import annotations

from collections.abc import Callable

BuildAuthorizeUrl = Callable[[str], str]


class StartGmailOAuth:
    """Delega a construção da URL de consentimento do Google a `build_authorize_url`."""

    def __init__(self, *, build_authorize_url: BuildAuthorizeUrl) -> None:
        """Recebe `build_authorize_url` por injeção (ver docstring do módulo)."""
        self._build_authorize_url = build_authorize_url

    def execute(self, state: str) -> str:
        """Devolve a URL de autorização do Google para `state`."""
        return self._build_authorize_url(state)
