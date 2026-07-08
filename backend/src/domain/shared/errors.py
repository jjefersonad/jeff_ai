"""Erros de domínio — levantados quando uma invariante de negócio é violada."""
from __future__ import annotations


class DomainError(Exception):
    """Falha de uma regra/invariante do domínio.

    Deve ser levantada na construção de entidades/value objects quando os dados
    são inválidos, antes de qualquer efeito colateral.
    """
