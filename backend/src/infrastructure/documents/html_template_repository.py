"""Repositório de templates HTML/CSS em filesystem + render Jinja2."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from src.domain.shared.errors import DomainError

# backend/templates/documents
_DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "templates" / "documents"


class FilesystemHtmlTemplateRepository:
    """Carrega `templates/documents/{name}/template.html` (+ `styles.css`)."""

    def __init__(self, *, root: Path | None = None) -> None:
        self._root = root or _DEFAULT_ROOT

    def render(self, name: str, data: dict[str, Any]) -> tuple[str, str | None]:
        """Renderiza o template nomeado; retorna `(html, css|None)`.

        Levanta `DomainError` se o template não existir.
        """
        safe = name.strip()
        if not safe or "/" in safe or "\\" in safe or ".." in safe:
            raise DomainError(f"Nome de template inválido: {name!r}.")
        template_dir = self._root / safe
        html_path = template_dir / "template.html"
        if not html_path.is_file():
            raise DomainError(f"Template não encontrado: {safe!r}.")

        env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )
        try:
            html = env.get_template("template.html").render(**data)
        except TemplateNotFound as exc:
            raise DomainError(f"Template não encontrado: {safe!r}.") from exc

        css_path = template_dir / "styles.css"
        css = css_path.read_text(encoding="utf-8") if css_path.is_file() else None
        return html, css
