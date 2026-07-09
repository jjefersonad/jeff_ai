"""Port de escrita de documentos — abstrai a biblioteca de geração e o destino."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.documents import DocumentResult, DocumentSpec


class DocumentWriterPort(ABC):
    """Cria e persiste um documento a partir de um `DocumentSpec`.

    A implementação concreta (infra) conhece a biblioteca (python-docx/openpyxl/
    python-pptx), o diretório de saída e a montagem da URL pública.
    """

    @abstractmethod
    async def write(self, spec: DocumentSpec) -> DocumentResult:
        """Gera o documento do `spec` e retorna caminho/URL/metadados."""
        raise NotImplementedError
