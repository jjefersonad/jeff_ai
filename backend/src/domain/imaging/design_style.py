"""Value object `DesignStyle` — a identidade visual reutilizável de uma imagem."""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.domain.shared.errors import DomainError

# Dimensões aceitas: "1080x1080" (largura x altura) ou proporção "16:9".
_DIMENSIONS_RE = re.compile(r"^\d+x\d+$|^\d+:\d+$")

_STRING_FIELDS = ("art_style", "color_palette", "composition", "dimensions")


@dataclass(frozen=True)
class DesignStyle:
    """Atributos estéticos de um design, independentes do assunto (prompt).

    É o que se reaproveita ao pedir "na mesma vibe": estilo artístico, paleta de
    cores, composição e dimensões. Todos os campos são opcionais, mas, quando
    informados, precisam ser strings não vazias (e `dimensions` num formato
    válido) — validado na construção.
    """

    art_style: str | None = None
    color_palette: str | None = None
    composition: str | None = None
    dimensions: str | None = None

    def __post_init__(self) -> None:
        """Valida e normaliza (strip) os campos informados."""
        for name in _STRING_FIELDS:
            value = getattr(self, name)
            if value is None:
                continue
            if not isinstance(value, str) or not value.strip():
                raise DomainError(
                    f"DesignStyle.{name} deve ser uma string não vazia quando informado."
                )
            object.__setattr__(self, name, value.strip())

        if self.dimensions is not None and not _DIMENSIONS_RE.match(self.dimensions):
            raise DomainError(
                f"DesignStyle.dimensions inválido: {self.dimensions!r} "
                "(use, por exemplo, '1080x1080' ou '16:9')."
            )

    def is_empty(self) -> bool:
        """Indica se nenhum atributo de estilo foi informado."""
        return all(getattr(self, name) is None for name in _STRING_FIELDS)
