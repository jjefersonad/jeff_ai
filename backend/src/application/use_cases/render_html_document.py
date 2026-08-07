"""Caso de uso: HTML/CSS → artefato final (`docx`/`xlsx`/`pptx`/`pdf`)."""
from __future__ import annotations

import datetime
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

from src.application.ports.html_document_converter import HtmlDocumentConverter
from src.domain.documents import DocumentResult
from src.domain.documents.html_sanitizer import sanitize_html
from src.domain.shared.errors import DomainError

_ALLOWED_KINDS = frozenset({"docx", "xlsx", "pptx", "pdf"})
_EXTENSIONS = {
    "docx": ".docx",
    "xlsx": ".xlsx",
    "pptx": ".pptx",
    "pdf": ".pdf",
}

OwnershipRecorder = Callable[[str, str], Awaitable[None] | None]


class RenderHtmlDocument:
    """Sanitiza HTML, converte pelo kind e grava só o artefato final.

    Não persiste HTML intermediário. Ownership é opcional e só roda após
    escrita bem-sucedida do arquivo final.
    """

    def __init__(
        self,
        *,
        converters: Mapping[str, HtmlDocumentConverter],
        output_base_dir: Path,
        url_prefix: str = "/api/files",
        record_ownership: OwnershipRecorder | None = None,
    ) -> None:
        self._converters = dict(converters)
        self._output_base_dir = output_base_dir
        self._url_prefix = url_prefix.rstrip("/")
        self._record_ownership = record_ownership

    async def execute(
        self,
        *,
        html: str,
        kind: str,
        css: str | None = None,
        title: str | None = None,
    ) -> DocumentResult:
        """Gera o documento do `kind` a partir de HTML/CSS."""
        if kind not in _ALLOWED_KINDS:
            raise DomainError(
                f"kind inválido: {kind!r}. Suportados: {sorted(_ALLOWED_KINDS)}."
            )
        converter = self._converters.get(kind)
        if converter is None:
            raise DomainError(f"Nenhum converter registrado para kind={kind!r}.")

        safe_html = sanitize_html(html)
        # Converter primeiro — falha não deixa arquivo parcial em disco.
        payload = await converter.convert(html=safe_html, css=css, kind=kind)

        kind_dir = self._output_base_dir / kind
        kind_dir.mkdir(parents=True, exist_ok=True)
        name = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f") + _EXTENSIONS[kind]
        path = kind_dir / name
        path.write_bytes(payload)
        url = f"{self._url_prefix}/{kind}/{name}"

        if self._record_ownership is not None:
            maybe_awaitable = self._record_ownership(kind, path.name)
            if maybe_awaitable is not None:
                await maybe_awaitable

        metadata: dict[str, object] = {"kind": kind}
        if title:
            metadata["title"] = title
        return DocumentResult(path=str(path), url=url, metadata=metadata)
