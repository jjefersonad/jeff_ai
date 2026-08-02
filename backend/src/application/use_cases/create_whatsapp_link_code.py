"""Caso de uso: gerar um código de vínculo WhatsApp para o usuário autenticado.

whatsapp-channel REQ-001: código single-use, 6 caracteres alfanuméricos, TTL de
10 minutos, atrelado ao `user_id` do chamador — nunca a um campo do corpo da
requisição. Mesmo formato/TTL de `CreateTelegramLinkCode`.
"""
from __future__ import annotations

import secrets
import string
from datetime import UTC, datetime, timedelta

from src.application.ports.whatsapp_link_code_repository import (
    WhatsAppLinkCodeRepositoryPort,
)
from src.domain.integrations import WhatsAppLinkCode

_CODE_LENGTH = 6
_TTL = timedelta(minutes=10)
_ALPHABET = string.ascii_uppercase + string.digits


def _generate_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LENGTH))


class CreateWhatsAppLinkCode:
    """Gera e persiste um `WhatsAppLinkCode` de 10 min de TTL para o chamador.

    Depende apenas da porta de repositório; não conhece Postgres nem
    qualquer adapter concreto.
    """

    def __init__(self, *, repository: WhatsAppLinkCodeRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção de dependência."""
        self._repository = repository

    async def execute(self, *, caller_user_id: str) -> WhatsAppLinkCode:
        """Gera um código novo tied ao `caller_user_id` e o persiste."""
        link_code = WhatsAppLinkCode(
            code=_generate_code(),
            user_id=caller_user_id,
            expires_at=datetime.now(UTC) + _TTL,
        )
        await self._repository.save(link_code)
        return link_code
