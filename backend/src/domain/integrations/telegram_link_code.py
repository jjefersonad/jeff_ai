"""Domínio da entidade `TelegramLinkCode`.

PURO: zero import de framework. Representa um código de vínculo Telegram
single-use e de TTL curto, gerado por `CreateTelegramLinkCode` e redimido por
`redeem_telegram_link_code` (task `user-integration-credentials-task-linking-1`)
para vincular um `chat_id` ao `user_id` que o gerou (design Decision 3 de
`user-integration-credentials`).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.shared.errors import DomainError


@dataclass
class TelegramLinkCode:
    """Um código de vínculo pertencente a um único `user_id`."""

    code: str
    user_id: str
    expires_at: datetime

    def __post_init__(self) -> None:
        """Valida que os campos identificadores obrigatórios não estão vazios."""
        for attr_name in ("code", "user_id"):
            value = getattr(self, attr_name)
            if not isinstance(value, str) or not value.strip():
                raise DomainError(
                    f"TelegramLinkCode.{attr_name} é obrigatório e não pode ser vazio."
                )
