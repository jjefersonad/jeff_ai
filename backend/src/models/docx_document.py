"""Schema Pydantic para a entrada estruturada da tool `create_docx_document`.

Modela o conteúdo de um documento Word (título + sequência de blocos) com um
formato tolerante (campos opcionais viram default no domínio). Vive em
`models/` porque é só contrato de borda da tool — não contém regra de negócio.
"""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _coerce_table_header_list(
    header: object,
    rows: List[List[str]] | None,
) -> tuple[bool, List[List[str]] | None]:
    """Normaliza `header` quando o LLM envia nomes de colunas como lista.

    Contrato canônico: `header` é bool e os nomes vão em `rows[0]`.
    Tolerância: `header=["Col A", "Col B"]` → prepend em `rows` + `header=True`.
    """
    if not isinstance(header, list):
        if header is None:
            return True, rows
        return bool(header), rows
    header_row = [str(cell) for cell in header]
    normalized_rows = [list(row) for row in (rows or [])]
    if not normalized_rows or [str(c) for c in normalized_rows[0]] != header_row:
        normalized_rows = [header_row, *normalized_rows]
    return True, normalized_rows


class DocxHeadingInput(BaseModel):
    """Heading (seção) do documento."""

    text: str = Field(description="Texto do heading (obrigatório).")
    level: int = Field(
        default=1,
        description="Nível hierárquico do heading (1 a 9). 1 = seção principal.",
    )


class DocxParagraphInput(BaseModel):
    """Parágrafo de texto simples."""

    text: str = Field(description="Texto do parágrafo (obrigatório).")


class DocxListInput(BaseModel):
    """Lista (ordenada ou não) de itens textuais."""

    items: List[str] = Field(
        description="Itens textuais da lista (nenhum pode ser vazio).",
    )
    ordered: bool = Field(
        default=False,
        description="Se True, usa lista numerada; senão, marcadores.",
    )


class DocxTableInput(BaseModel):
    """Tabela retangular de células textuais."""

    rows: List[List[str]] = Field(
        description="Linhas da tabela. Todas devem ter o mesmo número de colunas.",
    )
    header: bool | List[str] = Field(
        default=True,
        description=(
            "Preferência: bool — se True, a primeira linha de `rows` fica em "
            "negrito. Também aceita lista de nomes de colunas (será prependida "
            "em `rows` e tratada como header=True)."
        ),
    )

    @model_validator(mode="after")
    def _normalize_header(self) -> DocxTableInput:
        flag, rows = _coerce_table_header_list(self.header, self.rows)
        self.header = flag
        if rows is not None:
            self.rows = rows
        return self


class DocxImageInput(BaseModel):
    """Imagem em disco a ser embutida no documento."""

    path: str = Field(description="Caminho local do arquivo de imagem.")
    width_inches: float | None = Field(
        default=None,
        description="Largura da imagem em polegadas (omitir = tamanho original).",
    )


class DocxBlockInput(BaseModel):
    """Bloco genérico do documento — discriminated union leve via `type`."""

    type: str = Field(
        description="Tipo do bloco: 'heading' | 'paragraph' | 'list' | 'table' | 'image'.",
    )
    text: str | None = Field(
        default=None,
        description="Texto (heading/paragraph). Obrigatório para heading/paragraph.",
    )
    level: int | None = Field(
        default=None,
        description="Nível do heading (1 a 9). Usado quando type='heading'.",
    )
    items: List[str] | None = Field(
        default=None,
        description="Itens da lista. Usado quando type='list'.",
    )
    ordered: bool | None = Field(
        default=None,
        description="Lista ordenada? Usado quando type='list'.",
    )
    rows: List[List[str]] | None = Field(
        default=None,
        description=(
            "Linhas da tabela (type='table'). Inclua os nomes das colunas "
            "como primeira linha quando houver cabeçalho."
        ),
    )
    header: bool | List[str] | None = Field(
        default=None,
        description=(
            "type='table': preferência bool (True = 1ª linha de `rows` em "
            "negrito). Também aceita lista de nomes de colunas — nesse caso "
            "os nomes são prependidos em `rows` e header vira True. "
            "NÃO use lista se os nomes já estão em rows[0]."
        ),
    )
    path: str | None = Field(
        default=None,
        description="Caminho da imagem. Usado quando type='image'.",
    )
    width_inches: float | None = Field(
        default=None,
        description="Largura da imagem em polegadas. Usado quando type='image'.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "heading",
                "text": "Introdução",
                "level": 1,
            }
        }
    )

    @model_validator(mode="after")
    def _normalize_table_header(self) -> DocxBlockInput:
        if self.type != "table":
            return self
        flag, rows = _coerce_table_header_list(self.header, self.rows)
        self.header = flag
        self.rows = rows
        return self


class DocxDocumentInput(BaseModel):
    """Schema estruturado de entrada para `create_docx_document`.

    Aceita um título e uma lista de blocos genéricos (heading/paragraph/list/
    table/image) com tipo discriminado. Mantém um contrato tolerante: campos
    irrelevantes para o tipo do bloco são simplesmente ignorados.
    """

    title: str = Field(description="Título principal do documento.")
    blocks: List[DocxBlockInput] = Field(
        default_factory=list,
        description="Sequência ordenada de blocos do documento (pode ser vazia).",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Relatório de Status",
                "blocks": [
                    {"type": "heading", "text": "Resumo Executivo", "level": 1},
                    {"type": "paragraph", "text": "Este relatório resume os resultados do trimestre."},
                    {"type": "list", "items": ["Item A", "Item B", "Item C"], "ordered": False},
                ],
            }
        }
    )
