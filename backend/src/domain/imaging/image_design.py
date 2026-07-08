"""Entidade `ImageDesign` — um design de imagem planejado e pronto para gerar."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.imaging.design_style import DesignStyle
from src.domain.imaging.image_reference import ImageReference
from src.domain.shared.errors import DomainError


@dataclass(frozen=True)
class ImageDesign:
    """Um design de imagem completo: assunto (`prompt`) + estilo + o que evitar.

    `prompt` é obrigatório e não pode ser vazio. `style` carrega a identidade
    visual (ver `DesignStyle`); `negative_prompt` descreve o que deve ser evitado.
    `references` são imagens de referência (opcionais) que condicionam a geração
    para manter identidade visual — vazio por padrão (geração text-only).
    """

    prompt: str
    style: DesignStyle = field(default_factory=DesignStyle)
    negative_prompt: str | None = None
    references: tuple[ImageReference, ...] = ()

    def __post_init__(self) -> None:
        """Valida e normaliza o prompt, o negative_prompt e as referências."""
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            raise DomainError("ImageDesign.prompt é obrigatório e não pode ser vazio.")
        object.__setattr__(self, "prompt", self.prompt.strip())

        if self.negative_prompt is not None:
            if not isinstance(self.negative_prompt, str) or not self.negative_prompt.strip():
                raise DomainError(
                    "ImageDesign.negative_prompt deve ser não vazio quando informado."
                )
            object.__setattr__(self, "negative_prompt", self.negative_prompt.strip())

        # Normaliza qualquer iterável de referências para uma tupla imutável e valida
        # que todos os itens são ImageReference (o VO já garante o path não vazio).
        references = tuple(self.references)
        if not all(isinstance(ref, ImageReference) for ref in references):
            raise DomainError(
                "ImageDesign.references deve conter apenas objetos ImageReference."
            )
        object.__setattr__(self, "references", references)

    @property
    def has_references(self) -> bool:
        """Indica se há imagens de referência para condicionar a geração."""
        return bool(self.references)

    def metadata(self) -> dict[str, str | None]:
        """Retorna os metadados de design no formato usado na geração/sidecar."""
        return {
            "prompt": self.prompt,
            "art_style": self.style.art_style,
            "color_palette": self.style.color_palette,
            "composition": self.style.composition,
            "dimensions": self.style.dimensions,
            "negative_prompt": self.negative_prompt,
        }
