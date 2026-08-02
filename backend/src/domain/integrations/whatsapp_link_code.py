"""Domínio da entidade `WhatsAppLinkCode`.

PURO: zero import de framework. Representa um código de vínculo WhatsApp
single-use e de TTL curto, gerado por `CreateWhatsAppLinkCode` e redimido pelo
handler do webhook (`whatsapp-evolution-channel-task-linking-3`) para vincular
um `phone_number` ao `user_id` que o gerou — mesmo papel de `TelegramLinkCode`,
espelhando a Decision 4 de `whatsapp-evolution-channel-design`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.shared.errors import DomainError


@dataclass
class WhatsAppLinkCode:
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
                    f"WhatsAppLinkCode.{attr_name} é obrigatório e não pode ser vazio."
                )
