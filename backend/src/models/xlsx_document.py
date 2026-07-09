"""Schema Pydantic para a entrada estruturada da tool `create_xlsx_spreadsheet`.

Modela o conteúdo de uma planilha (uma ou mais abas) com um formato tolerante
(campos opcionais viram default no domínio). Vive em `models/` porque é só
contrato de borda da tool — não contém regra de negócio.
"""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field


class XlsxNumberFormatInput(BaseModel):
    """Formato numérico aplicado a uma coluna (índice 0-based)."""

    column: int = Field(description="Índice 0-based da coluna.")
    format: str = Field(
        description=(
            "Formato numérico estilo Excel (ex.: '0.00', '0%', '#,##0.00')."
        ),
    )


class XlsxSheetInput(BaseModel):
    """Uma aba da planilha."""

    name: str = Field(description="Nome da aba (obrigatório).")
    rows: List[List[str | int | float | None]] = Field(
        default_factory=list,
        description=(
            "Linhas da aba. Cada célula aceita str (texto ou fórmula começando com '='),"
            " int, float ou None (vazia)."
        ),
    )
    header: bool = Field(
        default=False,
        description="Se True, a primeira linha fica em negrito.",
    )
    column_widths: List[float] | None = Field(
        default=None,
        description="Larguras das colunas em ordem (valores positivos).",
    )
    number_formats: List[XlsxNumberFormatInput] = Field(
        default_factory=list,
        description="Formatos numéricos por coluna (índice 0-based).",
    )


class XlsxDocumentInput(BaseModel):
    """Schema estruturado de entrada para `create_xlsx_spreadsheet`.

    Aceita uma lista de abas. Mantém um contrato tolerante: blocos incompletos
    são ignorados pelo conversor da tool.
    """

    sheets: List[XlsxSheetInput] = Field(
        description="Abas da planilha (ao menos uma).",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "sheets": [
                    {
                        "name": "Vendas",
                        "rows": [
                            ["Mês", "Receita", "Custo"],
                            ["Janeiro", 12000, 8000],
                            ["Fevereiro", 15000, 9000],
                            ["Total", "=SUM(B2:B3)", "=SUM(C2:C3)"],
                        ],
                        "header": True,
                        "column_widths": [12, 14, 14],
                        "number_formats": [{"column": 1, "format": "#,##0.00"}],
                    },
                    {"name": "Resumo", "rows": [["OK"]]},
                ]
            }
        }
    )
