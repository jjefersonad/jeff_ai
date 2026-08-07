"""Caso de uso: persistir preview HTML servível (`kind=html`)."""
from __future__ import annotations

from pathlib import Path

from src.domain.documents import DocumentResult
from src.domain.documents.embed_css import make_self_contained_html
from src.domain.documents.html_sanitizer import sanitize_html
from src.domain.shared.errors import DomainError
from src.infrastructure.documents.output_target import DocumentOutput


class PreviewHtmlDocument:
    """Sanitiza HTML, embute CSS e grava em `documents/html/` com nome único."""

    def __init__(
        self,
        *,
        output_base_dir: Path,
        url_prefix: str = "/api/files",
    ) -> None:
        self._output = DocumentOutput(
            "html",
            output_dir=output_base_dir / "html",
            url_prefix=url_prefix,
        )

    def execute(
        self,
        *,
        html: str,
        css: str | None = None,
        title: str | None = None,
        template: str | None = None,
    ) -> DocumentResult:
        if not html or not html.strip():
            raise DomainError("HTML vazio: nada para pré-visualizar.")

        safe = sanitize_html(html)
        document = make_self_contained_html(safe, css)
        path, url = self._output.allocate(".html")
        path.write_text(document, encoding="utf-8")

        metadata: dict[str, object] = {"kind": "html"}
        if title:
            metadata["title"] = title
        if template:
            metadata["template"] = template
        metadata["filename"] = path.name
        return DocumentResult(path=str(path), url=url, metadata=metadata)
