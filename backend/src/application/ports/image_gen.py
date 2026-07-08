"""Port de geração de imagem — abstrai o provedor (ex.: Gemini) e o armazenamento."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.domain.imaging import ImageDesign


@dataclass(frozen=True)
class GeneratedImage:
    """Resultado da geração de uma imagem.

    `path` é o caminho interno no filesystem (uso interno); `url` é o endereço
    acessível pelo frontend (usado em markdown); `metadata` são os metadados de
    design (formato de `ImageDesign.metadata()`).
    """

    path: str
    url: str
    metadata: dict[str, str | None]


class ImageGenPort(ABC):
    """Gera e persiste uma imagem a partir de um `ImageDesign` aprovado."""

    @abstractmethod
    async def generate(self, design: ImageDesign) -> GeneratedImage:
        """Gera a imagem do `design` e retorna caminho/URL/metadados."""
        raise NotImplementedError
