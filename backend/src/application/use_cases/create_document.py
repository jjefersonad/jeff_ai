"""Caso de uso: criar um documento Office a partir de um `DocumentSpec`."""
from __future__ import annotations

from src.application.ports.document_writer import DocumentWriterPort
from src.domain.documents import DocumentResult, DocumentSpec


class CreateDocument:
    """Orquestra a criação de um documento delegando ao writer injetado.

    Não conhece python-docx/openpyxl/python-pptx nem o filesystem — depende só do
    port `DocumentWriterPort` e do domínio de `documents`.
    """

    def __init__(self, writer: DocumentWriterPort) -> None:
        """Recebe a implementação do port de escrita por injeção de dependência."""
        self._writer = writer

    async def execute(self, spec: DocumentSpec) -> DocumentResult:
        """Cria o documento do `spec` e retorna o resultado (path, url, metadata)."""
        return await self._writer.write(spec)
