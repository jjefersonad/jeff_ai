"""Conteúdo extraído de um documento lido (docx/xlsx/pptx/pdf).

Espelha `document_spec`, mas não o reutiliza: um `DocumentSpec` descreve *o que
escrever*, um `DocumentContent` descreve *o que se leu*. Os dois são assimétricos
— a leitura ganha metadados que a escrita não tem (`truncated`, totais,
`has_text_layer`) e perde a formatação que a escrita especifica.

Por isso as entidades daqui são **permissivas** onde as de escrita são estritas:
um `.docx` real tem parágrafos vazios, e recusá-los faria a leitura de um arquivo
perfeitamente válido levantar `DomainError`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Union

from src.domain.shared.errors import DomainError

#: Valor de célula lido de uma planilha. Mais amplo que o `CellValue` de escrita:
#: a leitura também encontra booleanos, e datas já normalizadas para texto.
ReadCellValue = Union[str, int, float, bool, None]

#: Formatos que o sistema sabe ler. `pdf` só entra como formato de ENTRADA — o
#: sistema não gera PDFs.
READABLE_KINDS: tuple[str, ...] = ("docx", "xlsx", "pptx", "pdf")


@dataclass(frozen=True)
class HeadingBlock:
    """Título lido, com o nível hierárquico que o documento declarava."""

    text: str
    level: int

    def __post_init__(self) -> None:
        """Valida o nível do heading; o texto pode ser vazio."""
        if not isinstance(self.text, str):
            raise DomainError("HeadingBlock.text deve ser uma string.")
        if not isinstance(self.level, int) or not 1 <= self.level <= 9:
            raise DomainError("HeadingBlock.level deve estar entre 1 e 9.")


@dataclass(frozen=True)
class ParagraphBlock:
    """Parágrafo lido. Diferente de `Paragraph` (escrita), aceita texto vazio."""

    text: str

    def __post_init__(self) -> None:
        """Valida apenas o tipo — um parágrafo vazio é conteúdo legítimo."""
        if not isinstance(self.text, str):
            raise DomainError("ParagraphBlock.text deve ser uma string.")


@dataclass(frozen=True)
class TableBlock:
    """Tabela lida. Diferente de `Table` (escrita), não exige ser retangular.

    Um documento gerado por outra ferramenta pode conter células mescladas que se
    projetam em linhas de larguras diferentes; recusá-lo impediria a leitura.
    """

    rows: tuple[tuple[str, ...], ...]

    def __post_init__(self) -> None:
        """Normaliza todas as células para `str`."""
        object.__setattr__(
            self, "rows", tuple(tuple(str(cell) for cell in row) for row in self.rows)
        )


@dataclass(frozen=True)
class SheetContent:
    """Uma aba lida de uma planilha.

    `total_rows` é a contagem real da aba no arquivo, mesmo quando `rows` vem
    truncado — é o que permite ao agente saber que a leitura foi parcial.
    """

    name: str
    rows: tuple[tuple[ReadCellValue, ...], ...]
    total_rows: int
    dimensions: str | None = None

    def __post_init__(self) -> None:
        """Valida o nome da aba e a contagem total de linhas."""
        if not isinstance(self.name, str) or not self.name:
            raise DomainError("SheetContent.name é obrigatório.")
        if not isinstance(self.total_rows, int) or self.total_rows < 0:
            raise DomainError("SheetContent.total_rows deve ser um inteiro >= 0.")
        object.__setattr__(self, "rows", tuple(tuple(row) for row in self.rows))


@dataclass(frozen=True)
class SlideContent:
    """Um slide lido: título opcional, textos e speaker notes.

    `notes` é string vazia quando o slide não tem notes slide — ausência de notas
    não é erro.
    """

    index: int
    title: str | None
    texts: tuple[str, ...]
    notes: str = ""

    def __post_init__(self) -> None:
        """Valida o índice e normaliza textos e notas."""
        if not isinstance(self.index, int) or self.index < 0:
            raise DomainError("SlideContent.index deve ser um inteiro >= 0.")
        if not isinstance(self.notes, str):
            raise DomainError("SlideContent.notes deve ser uma string (vazia se ausente).")
        object.__setattr__(self, "texts", tuple(self.texts))


@dataclass(frozen=True)
class PageContent:
    """Uma página lida de um PDF. `text` vazio é válido (página sem texto)."""

    number: int
    text: str

    def __post_init__(self) -> None:
        """Valida o número da página (base 1) e o tipo do texto."""
        if not isinstance(self.number, int) or self.number < 1:
            raise DomainError("PageContent.number deve ser um inteiro >= 1.")
        if not isinstance(self.text, str):
            raise DomainError("PageContent.text deve ser uma string.")


ContentBlock = Union[
    HeadingBlock, ParagraphBlock, TableBlock, SheetContent, SlideContent, PageContent
]


@dataclass(frozen=True)
class ReadMetadata:
    """Metadados de uma leitura — o que só existe depois de ler o arquivo.

    Os campos opcionais são específicos por formato e ficam ausentes do dicionário
    final quando não se aplicam. `truncated` sinaliza que os `ReadLimits` foram
    atingidos e o conteúdo veio parcial; os totais reportam sempre a contagem real
    do arquivo inteiro, nunca a do recorte retornado.
    """

    kind: str
    truncated: bool = False
    total_paragraphs: int | None = None
    total_tables: int | None = None
    total_slides: int | None = None
    page_count: int | None = None
    has_text_layer: bool | None = None
    has_uncomputed_formulas: bool | None = None
    title: str | None = None
    author: str | None = None

    def __post_init__(self) -> None:
        """Valida o formato e a não-negatividade dos totais informados."""
        if self.kind not in READABLE_KINDS:
            raise DomainError(f"ReadMetadata.kind deve ser um de {READABLE_KINDS}.")
        for name in ("total_paragraphs", "total_tables", "total_slides", "page_count"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or value < 0):
                raise DomainError(f"ReadMetadata.{name} deve ser um inteiro >= 0.")

    def to_dict(self) -> dict[str, Any]:
        """Serializa os metadados, omitindo os campos que não se aplicam ao formato."""
        data: dict[str, Any] = {"kind": self.kind, "truncated": self.truncated}
        optional = (
            "total_paragraphs",
            "total_tables",
            "total_slides",
            "page_count",
            "has_text_layer",
            "has_uncomputed_formulas",
            "title",
            "author",
        )
        for name in optional:
            value = getattr(self, name)
            if value is not None:
                data[name] = value
        return data


@dataclass(frozen=True)
class DocumentContent:
    """Conteúdo lido de um documento: blocos na ordem do arquivo e metadados.

    Não é um `DocumentSpec` e não pode ser passado a um `DocumentWriterPort` — um
    round-trip ler→escrever perderia a formatação em silêncio, o que é pior do que
    não existir.
    """

    #: Chaves do dicionário devolvido pelas tools de leitura. Deliberadamente sem
    #: `path`/`url`: a leitura não produz artefato novo para download.
    RESULT_KEYS: ClassVar[tuple[str, ...]] = ("content", "metadata")

    kind: str
    blocks: tuple[ContentBlock, ...]
    metadata: ReadMetadata

    def __post_init__(self) -> None:
        """Valida o formato e a coerência entre o conteúdo e seus metadados."""
        if self.kind not in READABLE_KINDS:
            raise DomainError(f"DocumentContent.kind deve ser um de {READABLE_KINDS}.")
        if self.metadata.kind != self.kind:
            raise DomainError("DocumentContent.metadata.kind diverge de DocumentContent.kind.")
        object.__setattr__(self, "blocks", tuple(self.blocks))
