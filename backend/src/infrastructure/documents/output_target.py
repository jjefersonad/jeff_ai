"""Resolução de diretório de saída e URL pública dos documentos gerados.

Compartilhado pelos writers de infraestrutura (docx/xlsx/pptx/pdf/html). No
layout session-file-sandbox o destino canônico é `files/<user_id>/docs/`
(flat); a URL pública permanece `/api/files/{kind}/{filename}`.
"""
from __future__ import annotations

import datetime
from pathlib import Path

# Fallback legado só para writers construídos sem output_dir explícito.
_DEFAULT_BASE = Path(__file__).resolve().parents[3] / "outputs" / "documents"


class DocumentOutput:
    """Aloca caminho de arquivo e URL pública para um tipo de documento."""

    def __init__(
        self,
        kind: str,
        *,
        output_dir: Path | None = None,
        url_prefix: str = "/api/files",
    ) -> None:
        """Configura o tipo (`docx`/`xlsx`/`pptx`/`pdf`), o destino e o prefixo de URL."""
        self._kind = kind
        self._dir = output_dir or (_DEFAULT_BASE / kind)
        self._url_prefix = url_prefix.rstrip("/")

    def allocate(self, extension: str) -> tuple[Path, str]:
        """Cria o diretório e retorna `(caminho, url)` com nome único por timestamp."""
        self._dir.mkdir(parents=True, exist_ok=True)
        name = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f") + extension
        return self._dir / name, f"{self._url_prefix}/{self._kind}/{name}"
