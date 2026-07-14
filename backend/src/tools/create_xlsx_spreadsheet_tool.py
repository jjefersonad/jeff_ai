"""Tool `create_xlsx_spreadsheet` — adapter fino sobre o caso de uso `CreateDocument`.

Borda deepagents: traduz a entrada (objeto `XlsxDocumentInput`) para o domínio
`XlsxSpec`, delega ao caso de uso via composição de dependências e devolve o
mesmo contrato `{path, url, metadata}` da tool de imagem.

NÃO contém regra de negócio — montagem/validação de abas e gravação em disco
vivem no domínio + writer de infraestrutura.
"""
from __future__ import annotations

from langchain_core.tools import tool

from src.composition.dependencies import build_create_document
from src.domain.documents import Sheet, XlsxSpec
from src.domain.shared.errors import DomainError
from src.infrastructure.documents import XlsxWriter
from src.models.xlsx_document import XlsxDocumentInput, XlsxSheetInput


def _to_sheet(raw: XlsxSheetInput) -> Sheet:
    """Constrói um `Sheet` a partir de um `XlsxSheetInput` (camada fina)."""
    return Sheet(
        name=raw.name,
        rows=tuple(tuple(row) for row in raw.rows),
        header=raw.header,
        column_widths=tuple(raw.column_widths) if raw.column_widths is not None else None,
        number_formats=tuple(
            (nf.column, nf.format) for nf in raw.number_formats
        ),
    )


def _to_xlsx_spec(payload: XlsxDocumentInput) -> XlsxSpec:
    """Constrói o `XlsxSpec` a partir do `XlsxDocumentInput` (camada fina)."""
    return XlsxSpec(sheets=tuple(_to_sheet(s) for s in payload.sheets))


@tool
async def create_xlsx_spreadsheet(payload: XlsxDocumentInput) -> dict:
    """Cria uma planilha (.xlsx) a partir de uma lista de abas estruturadas.

    Gera o `.xlsx` usando apenas a biblioteca Python `openpyxl` (sem `soffice`,
    `pandoc` ou Node) e devolve um dicionário com o mesmo contrato de
    `create_image_from_prompt`:
    - path: caminho local no filesystem (uso interno — NÃO mostrar ao usuário).
    - url: URL servida para download — SEMPRE usar em markdown para exibir o link.
    - metadata: metadados da planilha gerada (kind, nomes das abas).

    Cada aba aceita:
    - name (obrigatório) e rows (lista de listas; células str/int/float/None).
    - header (bool, default False): primeira linha em negrito.
    - column_widths (lista de floats, opcional): largura por coluna.
    - number_formats (lista de {column, format}, opcional): formato numérico por coluna.
    - Strings iniciadas por `=` são preservadas como fórmulas pelo openpyxl.

    Em caso de entrada inválida, retorna um dicionário com a chave `error`
    descrevendo o problema e nenhum arquivo parcial é deixado em disco.

    Example return:
    {"path": "/app/backend/outputs/documents/xlsx/20260708120000123456.xlsx",
     "url": "/api/files/xlsx/20260708120000123456.xlsx",
     "metadata": {"kind": "xlsx", "sheets": ["Vendas", "Resumo"]}}
    """
    try:
        spec = _to_xlsx_spec(payload)
    except DomainError as exc:
        return {"error": f"Entrada inválida: {exc}"}

    use_case = build_create_document(writer=XlsxWriter())
    result = await use_case.execute(spec)

    return {"path": result.path, "url": result.url, "metadata": result.metadata}
