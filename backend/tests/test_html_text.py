"""Testes de `html_to_text` (add-web-fetch-tool REQ-003)."""
from __future__ import annotations

from src.tools.html_text import html_to_text


def test_html_to_text_strips_script_and_style() -> None:
    """Unit-1: remove script/style e preserva texto de parágrafo."""
    html = """
    <html><head>
      <style>.x { color: red; }</style>
      <script>alert("xss")</script>
    </head><body>
      <p>Conteúdo visível</p>
    </body></html>
    """
    text = html_to_text(html)
    assert "Conteúdo visível" in text
    assert "alert" not in text
    assert "color: red" not in text
    assert "xss" not in text
