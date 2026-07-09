"""Resultado da geração de um documento (caminho, URL pública e metadados)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DocumentResult:
    """Resultado da criação de um documento Office.

    `path` é o caminho interno no filesystem (uso interno); `url` é o endereço
    servido para download pelo frontend; `metadata` descreve o conteúdo gerado.
    Mesmo contrato de retorno de `GeneratedImage` (imaging).
    """

    path: str
    url: str
    metadata: dict[str, Any]
