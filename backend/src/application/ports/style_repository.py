"""Port de repositório de estilos aprovados (memória de estilo por thread)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.imaging import ImageDesign


class StyleRepositoryPort(ABC):
    """Persiste e recupera o design aprovado por thread (reutilização "na mesma vibe")."""

    @abstractmethod
    async def save(
        self, thread_id: str, design: ImageDesign, image_path: str | None = None
    ) -> None:
        """Salva `design` como uma nova versão de estilo do thread.

        `image_path`, quando informado, guarda o caminho da imagem gerada para
        reuso posterior como referência visual ("na mesma vibe").
        """
        raise NotImplementedError

    @abstractmethod
    async def latest(self, thread_id: str) -> ImageDesign | None:
        """Retorna o design mais recente salvo no thread, ou None se não houver."""
        raise NotImplementedError

    @abstractmethod
    async def latest_image_path(self, thread_id: str) -> str | None:
        """Retorna o caminho da imagem gerada mais recente do thread, ou None.

        None quando não há nenhum registro com imagem (inclui registros legados
        gravados antes de o caminho da imagem passar a ser persistido).
        """
        raise NotImplementedError
