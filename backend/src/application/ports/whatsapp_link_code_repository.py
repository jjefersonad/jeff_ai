"""Port de repositório de códigos de vínculo WhatsApp.

whatsapp-channel REQ-001. Abstrai a persistência de `WhatsAppLinkCode`
(Postgres no adapter) do restante da camada de aplicação. `get()` retorna
`None` para código inexistente — é assim que o handler do webhook
(`whatsapp-evolution-channel-task-linking-3`) trata tanto código desconhecido
quanto já invalidado (mesma resposta) — mesmo contrato de
`TelegramLinkCodeRepositoryPort`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.integrations import WhatsAppLinkCode


class WhatsAppLinkCodeRepositoryPort(ABC):
    """Persiste `WhatsAppLinkCode`, um código single-use identificado por `code`."""

    @abstractmethod
    async def save(self, link_code: WhatsAppLinkCode) -> None:
        """Cria o código persistido (`code` é a chave primária)."""
        raise NotImplementedError

    @abstractmethod
    async def get(self, code: str) -> WhatsAppLinkCode | None:
        """Retorna o código pelo valor, ou `None` se inexistente/já invalidado.

        Nunca levanta exceção — o caller decide como comunicar isso.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete(self, code: str) -> None:
        """Remove o código (invalidação single-use). Tolerante a código inexistente."""
        raise NotImplementedError
