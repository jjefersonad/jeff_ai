"""Empacota CSS no HTML para preview self-contained."""
from __future__ import annotations


def make_self_contained_html(html: str, css: str | None) -> str:
    """Injeta `<style>` no documento quando há CSS; devolve HTML pronto para arquivo."""
    body = html.strip()
    if not css or not css.strip():
        return body

    style = f"<style>\n{css.strip()}\n</style>\n"
    lower = body.lower()
    head_close = lower.find("</head>")
    if head_close != -1:
        return body[:head_close] + style + body[head_close:]

    body_open = lower.find("<body")
    if body_open != -1:
        return (
            "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"utf-8\" />\n"
            f"{style}</head>\n{body[body_open:]}"
        )

    return (
        "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"utf-8\" />\n"
        f"{style}</head>\n<body>\n{body}\n</body>\n</html>"
    )
