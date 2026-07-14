"""Value object `ImageReference` — uma imagem de referência para condicionar a geração.

Aponta para um arquivo de imagem já resolvido no filesystem (`path`). Todas as
fontes de referência (URL baixada, upload, imagem anterior do thread) resolvem
para um `path` local ANTES de chegar ao domínio — aqui não há URL, bytes nem SDK.
Puro: sem framework, sem I/O.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.domain.shared.errors import DomainError


@dataclass(frozen=True)
class ImageReference:
    """Referência a uma imagem local usada para condicionar a geração.

    `path` é o caminho no filesystem da imagem de referência; obrigatório e não
    vazio. A leitura/decodificação do arquivo é responsabilidade da infraestrutura
    (adapter), não do domínio.
    """

    path: str

    def __post_init__(self) -> None:
        """Valida e normaliza (strip) o caminho."""
        if not isinstance(self.path, str) or not self.path.strip():
            raise DomainError("ImageReference.path é obrigatório e não pode ser vazio.")
        object.__setattr__(self, "path", self.path.strip())
