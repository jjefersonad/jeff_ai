"""Value object `FeatureNumber` — número sequencial de feature SDD."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from src.domain.shared.errors import DomainError


@dataclass(frozen=True, order=True)
class FeatureNumber:
    """Número sequencial e positivo de uma feature, formatado com zero-padding (>= 3 dígitos)."""

    value: int

    def __post_init__(self) -> None:
        """Valida que o número é um inteiro positivo."""
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise DomainError("FeatureNumber.value deve ser um inteiro.")
        if self.value < 1:
            raise DomainError("FeatureNumber.value deve ser >= 1.")

    def __str__(self) -> str:
        """Formata o número com zero-padding de no mínimo 3 dígitos (ex.: '001')."""
        return f"{self.value:03d}"

    @classmethod
    def parse(cls, text: str) -> FeatureNumber:
        """Interpreta uma string numérica (ex.: '001') como FeatureNumber."""
        if not isinstance(text, str) or not text.strip().isdigit():
            raise DomainError(f"FeatureNumber inválido: {text!r} (esperado dígitos).")
        return cls(int(text))

    @classmethod
    def first(cls) -> FeatureNumber:
        """Retorna o primeiro número da sequência (001)."""
        return cls(1)

    @classmethod
    def next_after(cls, existing: Iterable[FeatureNumber]) -> FeatureNumber:
        """Retorna o próximo número: max(existentes) + 1, ou 1 se não houver."""
        values = [n.value for n in existing]
        return cls(max(values) + 1 if values else 1)
