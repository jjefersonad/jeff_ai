"""Entidade `Feature` — uma feature SDD identificada por número + nome kebab-case."""
from __future__ import annotations

from dataclasses import dataclass

from src.domain.sdd.feature_number import FeatureNumber
from src.domain.shared.errors import DomainError


@dataclass(frozen=True)
class Feature:
    """Uma feature do pipeline SDD: um `FeatureNumber` e um nome (usado no diretório)."""

    number: FeatureNumber
    name: str

    def __post_init__(self) -> None:
        """Valida o nome (obrigatório, sem espaços internos nem '/')."""
        if not isinstance(self.name, str) or not self.name.strip():
            raise DomainError("Feature.name é obrigatório e não pode ser vazio.")
        name = self.name.strip()
        if any(ch.isspace() for ch in name) or "/" in name:
            raise DomainError("Feature.name não pode conter espaços internos nem '/'.")
        object.__setattr__(self, "name", name)

    @property
    def directory_name(self) -> str:
        """Nome do diretório da feature: '{NNN}-{nome}' (ex.: '001-user-authentication')."""
        return f"{self.number}-{self.name}"
