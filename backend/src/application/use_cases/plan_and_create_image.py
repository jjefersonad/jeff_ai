"""Caso de uso: planejar e gerar uma imagem (após aprovação do usuário)."""
from __future__ import annotations

from src.application.ports.image_gen import GeneratedImage, ImageGenPort
from src.application.ports.style_repository import StyleRepositoryPort
from src.domain.imaging import ImageDesign, ImageReference, same_vibe


class PlanAndCreateImage:
    """Orquestra a geração de imagem a partir de um `ImageDesign` aprovado.

    A APROVAÇÃO do usuário acontece FORA deste caso de uso (na borda deepagents,
    via interrupt) — aqui a execução só ocorre depois de aprovada. Depende apenas
    do domínio de imaging e dos ports; não conhece Gemini, o Store nem deepagents.
    """

    def __init__(self, image_gen: ImageGenPort, styles: StyleRepositoryPort) -> None:
        """Recebe as implementações dos ports por injeção de dependência."""
        self._image_gen = image_gen
        self._styles = styles

    async def execute(
        self,
        design: ImageDesign,
        *,
        thread_id: str | None = None,
        remember_style: bool = False,
    ) -> GeneratedImage:
        """Gera a imagem do `design`; se `remember_style`, persiste o estilo no thread.

        Args:
            design: O design aprovado a ser gerado.
            thread_id: Thread da conversa (obrigatório se `remember_style`).
            remember_style: Se True, salva o design como estilo do thread para
                reutilização posterior ("na mesma vibe").

        Returns:
            O resultado da geração (caminho, URL e metadados).
        """
        result = await self._image_gen.generate(design)
        if remember_style:
            if not thread_id:
                raise ValueError("thread_id é obrigatório para lembrar o estilo.")
            await self._styles.save(thread_id, design, image_path=result.path)
        return result

    async def prepare_same_vibe(
        self,
        thread_id: str,
        new_prompt: str,
        negative_prompt: str | None = None,
    ) -> ImageDesign | None:
        """Monta um novo `ImageDesign` reutilizando o estilo mais recente do thread.

        Quando há uma imagem anterior salva no thread, ela é incluída como
        referência visual para reforçar a consistência ("na mesma vibe"). Se não
        houver imagem anterior, reutiliza apenas o estilo textual (fallback).
        Retorna None se ainda não houver estilo salvo para o thread.
        """
        previous = await self._styles.latest(thread_id)
        if previous is None:
            return None
        image_path = await self._styles.latest_image_path(thread_id)
        references = (ImageReference(path=image_path),) if image_path else ()
        return same_vibe(previous, new_prompt, negative_prompt, references=references)
