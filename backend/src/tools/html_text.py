"""Conversão HTML → texto visível (stdlib HTMLParser).

Compartilhado por `web_fetch` e `ingest_document` — remove script/style e
devolve o texto legível sem markup.
"""
from __future__ import annotations

from html.parser import HTMLParser


class _TextExtractingHTMLParser(HTMLParser):
    """Extrai o texto visível de um HTML, descartando script/style/etc."""

    _SKIP_TAGS = {"script", "style", "noscript", "template"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self._parts.append(text)

    def get_text(self) -> str:
        return "\n".join(self._parts)


def html_to_text(html: str) -> str:
    """Converte HTML em texto limpo, sem script/style."""
    parser = _TextExtractingHTMLParser()
    parser.feed(html)
    return parser.get_text()
