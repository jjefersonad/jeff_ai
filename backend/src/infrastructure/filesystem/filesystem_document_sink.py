"""Adapter de filesystem para consolidação de documentos (`DocumentSinkPort`)."""
from __future__ import annotations

from pathlib import Path

from src.application.ports.document_sink import DocumentSinkPort
from src.domain.requirements import DocumentSection


class FilesystemDocumentSink(DocumentSinkPort):
    """Lê seções de arquivos de um diretório e grava o documento consolidado nele."""

    def __init__(self, base_dir: str | Path) -> None:
        """Vincula o sink ao diretório de saída (ex.: `outputs/{thread_id}`)."""
        self._base = Path(base_dir).resolve()

    def collect_sections(self, *, exclude: str | None = None) -> list[DocumentSection]:
        """Lê cada arquivo do diretório (exceto `exclude`) como uma `DocumentSection`."""
        files = [
            f
            for f in self._base.iterdir()
            if f.is_file() and f.name != exclude
        ]
        return [
            DocumentSection(f.name, f.read_text(encoding="utf-8"))
            for f in files
        ]

    def write(self, filename: str, content: str) -> str:
        """Grava `content` em `<base>/<filename>` e retorna o caminho absoluto."""
        path = self._base / filename
        path.write_text(content, encoding="utf-8")
        return str(path)
