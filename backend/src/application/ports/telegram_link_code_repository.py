"""Port de repositório de códigos de vínculo Telegram.

REQ-001 do spec `user-integration-credentials-telegram-account-linking`.
Abstrai a persistência de `TelegramLinkCode` (Postgres no adapter) do
restante da camada de aplicação. `get()` retorna `None` para código
inexistente — é assim que `RedeemTelegramLinkCode` (task
`user-integration-credentials-task-linking-1`) trata tanto código
desconhecido quanto já invalidado (mesma resposta, REQ-002 cenários 2/3).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.integrations import TelegramLinkCode


class TelegramLinkCodeRepositoryPort(ABC):
    """Persiste `TelegramLinkCode`, um código single-use identificado por `code`."""

    @abstractmethod
    async def save(self, link_code: TelegramLinkCode) -> None:
        """Cria o código persistido (`code` é a chave primária)."""
        raise NotImplementedError

    @abstractmethod
    async def get(self, code: str) -> TelegramLinkCode | None:
        """Retorna o código pelo valor, ou `None` se inexistente/já invalidado.

        Nunca levanta exceção — o caller decide como comunicar isso.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete(self, code: str) -> None:
        """Remove o código (invalidação single-use). Tolerante a código inexistente."""
        raise NotImplementedError
