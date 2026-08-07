"""Port: converte HTML/CSS sanitizado em bytes do formato alvo (`kind`)."""
from __future__ import annotations

from abc import ABC, abstractmethod


class HtmlDocumentConverter(ABC):
    """Gera o payload binário de um documento a partir de HTML/CSS.

    A implementação (infra) conhece WeasyPrint / python-docx / etc. O caso de
    uso decide kind, sanitização, persistência e ownership.
    """

    @abstractmethod
    async def convert(self, *, html: str, css: str | None, kind: str) -> bytes:
        """Converte `html` (+ `css` opcional) para bytes do `kind` pedido."""
        raise NotImplementedError
