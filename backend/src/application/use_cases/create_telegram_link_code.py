"""Caso de uso: gerar um código de vínculo Telegram para o usuário autenticado.

REQ-001 do spec `user-integration-credentials-telegram-account-linking`: código
single-use, 6 caracteres alfanuméricos, TTL de 10 minutos, atrelado ao
`user_id` do chamador — nunca a um campo do corpo da requisição.
"""
from __future__ import annotations

import secrets
import string
from datetime import UTC, datetime, timedelta

from src.application.ports.telegram_link_code_repository import (
    TelegramLinkCodeRepositoryPort,
)
from src.domain.integrations import TelegramLinkCode

_CODE_LENGTH = 6
_TTL = timedelta(minutes=10)
_ALPHABET = string.ascii_uppercase + string.digits


def _generate_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LENGTH))


class CreateTelegramLinkCode:
    """Gera e persiste um `TelegramLinkCode` de 10 min de TTL para o chamador.

    Depende apenas da porta de repositório; não conhece Postgres nem
    qualquer adapter concreto.
    """

    def __init__(self, *, repository: TelegramLinkCodeRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção de dependência."""
        self._repository = repository

    async def execute(self, *, caller_user_id: str) -> TelegramLinkCode:
        """Gera um código novo tied ao `caller_user_id` e o persiste."""
        link_code = TelegramLinkCode(
            code=_generate_code(),
            user_id=caller_user_id,
            expires_at=datetime.now(UTC) + _TTL,
        )
        await self._repository.save(link_code)
        return link_code
