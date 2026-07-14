"""Spec de conteúdo de uma apresentação (`.pptx`) a ser criada."""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Union

from src.domain.documents.blocks import ImageRef, Table
from src.domain.shared.errors import DomainError


@dataclass(frozen=True)
class TitleSlide:
    """Slide de título (capa), com subtítulo opcional."""

    title: str
    subtitle: str | None = None

    def __post_init__(self) -> None:
        """Valida o título e normaliza o subtítulo."""
        if not isinstance(self.title, str) or not self.title.strip():
            raise DomainError("TitleSlide.title é obrigatório e não pode ser vazio.")
        object.__setattr__(self, "title", self.title.strip())
        if self.subtitle is not None:
            if not isinstance(self.subtitle, str) or not self.subtitle.strip():
                raise DomainError("TitleSlide.subtitle deve ser não vazio quando informado.")
            object.__setattr__(self, "subtitle", self.subtitle.strip())


@dataclass(frozen=True)
class BulletSlide:
    """Slide de conteúdo com um título e uma lista de bullets."""

    title: str
    bullets: tuple[str, ...]

    def __post_init__(self) -> None:
        """Valida o título e os bullets (nenhum vazio)."""
        if not isinstance(self.title, str) or not self.title.strip():
            raise DomainError("BulletSlide.title é obrigatório e não pode ser vazio.")
        object.__setattr__(self, "title", self.title.strip())
        bullets = tuple(b.strip() for b in self.bullets if isinstance(b, str))
        if len(bullets) != len(self.bullets) or not bullets or any(not b for b in bullets):
            raise DomainError("BulletSlide.bullets deve conter apenas strings não vazias.")
        object.__setattr__(self, "bullets", bullets)


@dataclass(frozen=True)
class ImageSlide:
    """Slide com uma imagem embutida e um título opcional."""

    image: ImageRef
    title: str | None = None

    def __post_init__(self) -> None:
        """Valida a imagem e normaliza o título."""
        if not isinstance(self.image, ImageRef):
            raise DomainError("ImageSlide.image deve ser um ImageRef.")
        if self.title is not None:
            if not isinstance(self.title, str) or not self.title.strip():
                raise DomainError("ImageSlide.title deve ser não vazio quando informado.")
            object.__setattr__(self, "title", self.title.strip())


@dataclass(frozen=True)
class TableSlide:
    """Slide com uma tabela simples e um título opcional."""

    table: Table
    title: str | None = None

    def __post_init__(self) -> None:
        """Valida a tabela e normaliza o título."""
        if not isinstance(self.table, Table):
            raise DomainError("TableSlide.table deve ser um Table.")
        if self.title is not None:
            if not isinstance(self.title, str) or not self.title.strip():
                raise DomainError("TableSlide.title deve ser não vazio quando informado.")
            object.__setattr__(self, "title", self.title.strip())


Slide = Union[TitleSlide, BulletSlide, ImageSlide, TableSlide]


@dataclass(frozen=True)
class PptxSpec:
    """Apresentação a criar: uma sequência ordenada de slides."""

    kind: ClassVar[str] = "pptx"
    extension: ClassVar[str] = ".pptx"

    slides: tuple[Slide, ...]

    def __post_init__(self) -> None:
        """Valida que há ao menos um slide e que todos são tipos suportados."""
        slides = tuple(self.slides)
        if not slides:
            raise DomainError("PptxSpec.slides deve conter ao menos um slide.")
        allowed = (TitleSlide, BulletSlide, ImageSlide, TableSlide)
        if not all(isinstance(slide, allowed) for slide in slides):
            raise DomainError("PptxSpec.slides contém um tipo de slide não suportado.")
        object.__setattr__(self, "slides", slides)

    def metadata(self) -> dict[str, object]:
        """Retorna os metadados da apresentação para o resultado da geração."""
        return {"kind": self.kind, "slide_count": len(self.slides)}
