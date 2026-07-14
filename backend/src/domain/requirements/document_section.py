"""Value object `DocumentSection` — uma seção nomeada do documento de requisitos."""
from __future__ import annotations

from dataclasses import dataclass

from src.domain.shared.errors import DomainError


@dataclass(frozen=True)
class DocumentSection:
    """Uma seção do documento: um nome (ex.: nome do arquivo gerado) e seu conteúdo.

    `name` é obrigatório; `content` pode ser vazio, mas deve ser string.
    """

    name: str
    content: str

    def __post_init__(self) -> None:
        """Valida o nome (obrigatório, não vazio) e o tipo do conteúdo."""
        if not isinstance(self.name, str) or not self.name.strip():
            raise DomainError("DocumentSection.name é obrigatório e não pode ser vazio.")
        object.__setattr__(self, "name", self.name.strip())
        if not isinstance(self.content, str):
            raise DomainError("DocumentSection.content deve ser uma string.")
