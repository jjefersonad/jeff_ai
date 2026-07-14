"""Tool `create_pptx_presentation` — adapter fino sobre o caso de uso `CreateDocument`.

Borda deepagents: traduz a entrada (`PptxDocumentInput`) para o domínio
`PptxSpec`, delega ao caso de uso via composição de dependências e devolve o
mesmo contrato `{path, url, metadata}` da tool de imagem.

NÃO contém regra de negócio — montagem/validação de slides e gravação em disco
vivem no domínio + writer de infraestrutura.
"""
from __future__ import annotations

from langchain_core.tools import tool

from src.composition.dependencies import build_create_document
from src.domain.documents import (
    BulletSlide,
    ImageRef,
    ImageSlide,
    PptxSpec,
    Table,
    TableSlide,
    TitleSlide,
)
from src.domain.shared.errors import DomainError
from src.infrastructure.documents import PptxWriter
from src.models.pptx_document import PptxDocumentInput, PptxSlideInput


def _to_slide(raw: PptxSlideInput) -> object | None:
    """Constrói um value object de slide a partir de um `PptxSlideInput`.

    Retorna `None` quando os campos obrigatórios para o tipo estão ausentes —
    o conversor da tool descarta esses slides silenciosamente (contrato
    tolerante) em vez de levantar erro.
    """
    kind = raw.type
    if kind == "title":
        if not raw.title:
            return None
        return TitleSlide(title=raw.title, subtitle=raw.subtitle)
    if kind == "bullets":
        if not raw.title or not raw.bullets:
            return None
        return BulletSlide(title=raw.title, bullets=tuple(raw.bullets))
    if kind == "image":
        if not raw.path:
            return None
        return ImageSlide(
            image=ImageRef(path=raw.path, width_inches=raw.width_inches),
            title=raw.title,
        )
    if kind == "table":
        if not raw.rows:
            return None
        return TableSlide(
            table=Table(
                rows=tuple(tuple(row) for row in raw.rows),
                header=bool(raw.header) if raw.header is not None else True,
            ),
            title=raw.title,
        )
    # tipo desconhecido: ignorado silenciosamente (contrato tolerante).
    return None


def _to_pptx_spec(payload: PptxDocumentInput) -> PptxSpec:
    """Constrói o `PptxSpec` a partir do `PptxDocumentInput` (camada fina)."""
    slides = tuple(s for s in (_to_slide(raw) for raw in payload.slides) if s is not None)
    return PptxSpec(slides=slides)


@tool
async def create_pptx_presentation(payload: PptxDocumentInput) -> dict:
    """Cria uma apresentação (.pptx) a partir de uma sequência de slides.

    Gera o `.pptx` usando apenas a biblioteca Python `python-pptx` (sem
    `soffice`, `pandoc` ou Node) e devolve um dicionário com o mesmo contrato de
    `create_image_from_prompt`:
    - path: caminho local no filesystem (uso interno — NÃO mostrar ao usuário).
    - url: URL servida para download — SEMPRE usar em markdown para exibir o link.
    - metadata: metadados da apresentação gerada (kind, contagem de slides).

    Tipos de slide suportados:
    - 'title': capa com título (e subtítulo opcional).
    - 'bullets': slide de conteúdo com título e lista de bullets.
    - 'image': slide com imagem embutida (e título opcional).
    - 'table': slide com tabela simples (e título opcional).

    Slides com `type` desconhecido ou com campos obrigatórios faltando são
    descartados (contrato tolerante). Em caso de entrada inválida global
    (ex.: nenhum slide válido), retorna um dicionário com `error` e nenhum
    arquivo parcial é deixado em disco.

    Example return:
    {"path": "/app/backend/outputs/documents/pptx/20260708120000123456.pptx",
     "url": "/api/files/pptx/20260708120000123456.pptx",
     "metadata": {"kind": "pptx", "slide_count": 3}}
    """
    try:
        spec = _to_pptx_spec(payload)
    except DomainError as exc:
        return {"error": f"Entrada inválida: {exc}"}

    use_case = build_create_document(writer=PptxWriter())
    result = await use_case.execute(spec)

    return {"path": result.path, "url": result.url, "metadata": result.metadata}
