"""Converte blocos legados (heading/paragraph/list/table/image) em HTML semântico."""
from __future__ import annotations

import html
from typing import Sequence


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def blocks_to_html(*, title: str | None, blocks: Sequence[object]) -> str:
    """Monta um fragmento/documento HTML a partir de title + blocos tipo tool input.

    Aceita objetos com atributos no estilo `HtmlBlockInput` / `PdfBlockInput`
    (`type`, `text`, `level`, `items`, `ordered`, `rows`, `header`, `path`).
    """
    parts: list[str] = ['<!DOCTYPE html><html><head><meta charset="utf-8">']
    if title and title.strip():
        parts.append(f"<title>{_escape(title.strip())}</title>")
    parts.append("</head><body>")
    if title and title.strip():
        parts.append(f"<h1>{_escape(title.strip())}</h1>")

    for block in blocks:
        kind = getattr(block, "type", None)
        if kind == "heading":
            text = getattr(block, "text", None)
            if not text:
                continue
            level = int(getattr(block, "level", None) or 1)
            level = min(max(level, 1), 6)
            parts.append(f"<h{level}>{_escape(text)}</h{level}>")
        elif kind == "paragraph":
            text = getattr(block, "text", None)
            if not text:
                continue
            parts.append(f"<p>{_escape(text)}</p>")
        elif kind == "list":
            items = getattr(block, "items", None) or []
            if not items:
                continue
            tag = "ol" if getattr(block, "ordered", False) else "ul"
            parts.append(f"<{tag}>")
            for item in items:
                parts.append(f"<li>{_escape(str(item))}</li>")
            parts.append(f"</{tag}>")
        elif kind == "table":
            rows = getattr(block, "rows", None) or []
            if not rows:
                continue
            header = getattr(block, "header", None)
            use_header = True if header is None else bool(header)
            parts.append("<table>")
            for idx, row in enumerate(rows):
                parts.append("<tr>")
                cell_tag = "th" if use_header and idx == 0 else "td"
                for cell in row:
                    parts.append(f"<{cell_tag}>{_escape(str(cell))}</{cell_tag}>")
                parts.append("</tr>")
            parts.append("</table>")
        elif kind == "image":
            path = getattr(block, "path", None)
            if not path:
                continue
            parts.append(f'<img src="{_escape(str(path))}" alt="" />')

    parts.append("</body></html>")
    return "".join(parts)
