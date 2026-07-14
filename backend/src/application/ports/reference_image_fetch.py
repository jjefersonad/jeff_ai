"""Port de busca de imagem de referência por URL.

Abstrai o download + validação de uma imagem remota, entregando um caminho
local pronto para virar `ImageReference`. A implementação (rede/validação) vive
na `infrastructure`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class ReferenceImageFetchError(Exception):
    """Falha ao buscar/validar uma imagem de referência remota (URL inválida/insegura)."""


class ReferenceImageFetchPort(ABC):
    """Baixa uma imagem de uma URL, valida-a e a salva localmente."""

    @abstractmethod
    async def fetch(self, url: str) -> str:
        """Baixa e valida a imagem em `url`, salva localmente e retorna o path.

        Levanta `ReferenceImageFetchError` quando a URL é inacessível, não retorna
        conteúdo de imagem suportado, excede o tamanho máximo, tem esquema não
        permitido, ou aponta para host privado/loopback (SSRF).
        """
        raise NotImplementedError
