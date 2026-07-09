"""Tool `create_docx_document` — adapter fino sobre o caso de uso `CreateDocument`.

Borda deepagents: traduz a entrada (string simples ou `DocxDocumentInput`) para
o domínio `DocxSpec`, delega ao caso de uso via composição de dependências e
devolve o mesmo contrato `{path, url, metadata}` da tool de imagem.

NÃO contém regra de negócio — montagem/validação de blocos e gravação em
disco vivem no domínio + writer de infraestrutura.
"""
from __future__ import annotations

from typing import Union

from langchain_core.tools import tool

from src.composition.dependencies import build_create_document
from src.domain.documents import (
    DocxSpec,
    Heading,
    ImageRef,
    ListBlock,
    Paragraph,
    Table,
)
from src.domain.shared.errors import DomainError
from src.models.docx_document import DocxBlockInput, DocxDocumentInput


def _to_blocks(raw_blocks: list[DocxBlockInput]) -> tuple[object, ...]:
    """Convert blocks to domain value objects.

    Mantém o contrato tolerante da tool: blocos com `type` desconhecido são
    ignorados (não levantam erro) para que o LLM consiga enviar entradas
    aproximadas sem quebrar a geração. A validação semântica fina é feita pelo
    domínio na construção de cada value object.
    """
    rendered: list[object] = []
    for block in raw_blocks:
        kind = block.type
        if kind == "heading":
            if not block.text:
                continue
            rendered.append(Heading(text=block.text, level=block.level or 1))
        elif kind == "paragraph":
            if not block.text:
                continue
            rendered.append(Paragraph(text=block.text))
        elif kind == "list":
            if not block.items:
                continue
            rendered.append(
                ListBlock(items=tuple(block.items), ordered=bool(block.ordered)),
            )
        elif kind == "table":
            if not block.rows:
                continue
            rendered.append(
                Table(
                    rows=tuple(tuple(row) for row in block.rows),
                    header=bool(block.header) if block.header is not None else True,
                ),
            )
        elif kind == "image":
            if not block.path:
                continue
            rendered.append(
                ImageRef(path=block.path, width_inches=block.width_inches),
            )
        # tipo desconhecido: ignorado silenciosamente (contrato tolerante).
    return tuple(rendered)


def _to_docx_spec(payload: Union[str, DocxDocumentInput]) -> DocxSpec:
    """Constrói o `DocxSpec` a partir da entrada (string simples ou input estruturado).

    String → documento só com o título. DocxDocumentInput → título + blocos
    convertidos via `_to_blocks`.
    """
    if isinstance(payload, str):
        return DocxSpec(title=payload)
    return DocxSpec(title=payload.title, blocks=_to_blocks(payload.blocks))


@tool
async def create_docx_document(
    payload: Union[str, DocxDocumentInput],
) -> dict:
    """Cria um documento Word (.docx) a partir de um título e blocos estruturados.

    Gera o `.docx` usando apenas a biblioteca Python `python-docx` (sem `pandoc`,
    `soffice` ou Node) e devolve um dicionário com o mesmo contrato de
    `create_image_from_prompt`:
    - path: caminho local no filesystem (uso interno — NÃO mostrar ao usuário).
    - url: URL servida para download — SEMPRE usar em markdown para exibir o link.
    - metadata: metadados do documento gerado (kind, título, contagem de blocos).

    Aceita entrada tolerante:
    - string simples → documento com apenas o título (modo legado).
    - DocxDocumentInput (Pydantic) com `title` e `blocks` (heading/paragraph/
      list/table/image). Blocos com `type` desconhecido são ignorados.

    Em caso de entrada inválida, retorna um dicionário com a chave `error`
    descrevendo o problema e nenhum arquivo parcial é deixado em disco.

    Example return:
    {"path": "/app/backend/outputs/documents/docx/20260708120000123456.docx",
     "url": "/api/files/docx/20260708120000123456.docx",
     "metadata": {"kind": "docx", "title": "Relatório", "block_count": 3}}
    """
    try:
        spec = _to_docx_spec(payload)
    except DomainError as exc:
        return {"error": f"Entrada inválida: {exc}"}

    use_case = build_create_document()
    result = await use_case.execute(spec)

    return {"path": result.path, "url": result.url, "metadata": result.metadata}
