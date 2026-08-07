"""Sanitização de HTML antes do render HTML→documento.

Remove `<script>`/`<iframe>`/`<object>`/`<embed>`/`form` e URLs `javascript:` /
`vbscript:` / `data:` em atributos de URI. Stdlib only (`html.parser`).
"""
from __future__ import annotations

from html.parser import HTMLParser
from typing import List


_STRIP_TAGS = frozenset({"script", "iframe", "object", "embed", "form"})
_URI_ATTRS = frozenset({"href", "src", "xlink:href", "action", "formaction", "poster"})
_DANGEROUS_URI_PREFIXES = ("javascript:", "vbscript:", "data:")


def _is_dangerous_uri(value: str) -> bool:
    return value.lstrip().lower().startswith(_DANGEROUS_URI_PREFIXES)


class _SanitizingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        if lower in _STRIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        safe_attrs: list[str] = []
        for name, value in attrs:
            if value is None:
                safe_attrs.append(name)
                continue
            if name.lower().startswith("on"):
                continue
            if name.lower() in _URI_ATTRS and _is_dangerous_uri(value):
                continue
            safe_attrs.append(f'{name}="{value}"')
        attr_str = (" " + " ".join(safe_attrs)) if safe_attrs else ""
        self._parts.append(f"<{tag}{attr_str}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        if lower in _STRIP_TAGS or self._skip_depth:
            return
        safe_attrs: list[str] = []
        for name, value in attrs:
            if value is None:
                safe_attrs.append(name)
                continue
            if name.lower().startswith("on"):
                continue
            if name.lower() in _URI_ATTRS and _is_dangerous_uri(value):
                continue
            safe_attrs.append(f'{name}="{value}"')
        attr_str = (" " + " ".join(safe_attrs)) if safe_attrs else ""
        self._parts.append(f"<{tag}{attr_str} />")

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower in _STRIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        self._parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self._parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._skip_depth:
            return
        self._parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._skip_depth:
            return
        self._parts.append(f"&#{name};")

    def result(self) -> str:
        return "".join(self._parts)


def sanitize_html(html: str) -> str:
    """Retorna HTML sem scripts/handlers/URIs perigosas."""
    parser = _SanitizingParser()
    parser.feed(html)
    parser.close()
    return parser.result()
