"""Caso de uso: consolidar as seções geradas num documento de requisitos final."""
from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.document_sink import DocumentSinkPort
from src.domain.requirements import consolidate


@dataclass(frozen=True)
class ConsolidationResult:
    """Resultado da consolidação: caminho do arquivo final e nº de seções unificadas.

    `path` é vazio e `section_count` é 0 quando não havia seções para unificar
    (nesse caso nada é gravado).
    """

    path: str
    section_count: int


class GenerateRequirementsDocument:
    """Coleta as seções via `DocumentSinkPort`, aplica a regra de merge e persiste.

    Depende apenas do domínio de requirements e do port; não conhece filesystem,
    LangGraph nem deepagents.
    """

    def __init__(self, sink: DocumentSinkPort) -> None:
        """Recebe a implementação do port por injeção de dependência."""
        self._sink = sink

    def execute(self, final_filename: str) -> ConsolidationResult:
        """Consolida as seções (exceto o próprio final) e grava o documento.

        Se não houver seções, não grava nada e retorna `section_count == 0`
        (preserva o comportamento do merge legado).
        """
        sections = self._sink.collect_sections(exclude=final_filename)
        if not sections:
            return ConsolidationResult(path="", section_count=0)

        document = consolidate(sections)
        path = self._sink.write(final_filename, document.render())
        return ConsolidationResult(path=path, section_count=len(sections))
