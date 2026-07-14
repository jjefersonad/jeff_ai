"""Port do workspace de documentos — lê as seções-fonte e grava o consolidado."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.requirements import DocumentSection


class DocumentSinkPort(ABC):
    """Abstrai o I/O de consolidação: coletar as seções-fonte e persistir o resultado.

    A implementação concreta está ligada a um local (ex.: um diretório de saída).
    """

    @abstractmethod
    def collect_sections(self, *, exclude: str | None = None) -> list[DocumentSection]:
        """Lê as seções-fonte do local, ignorando o arquivo `exclude` (o consolidado)."""
        raise NotImplementedError

    @abstractmethod
    def write(self, filename: str, content: str) -> str:
        """Grava `content` em `filename` no local e retorna o caminho final (str)."""
        raise NotImplementedError
