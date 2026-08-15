---
name: xlsx
description: "Use this skill any time the user wants to CREATE a new spreadsheet (.xlsx). Generation uses the HTML pipeline (`create_xlsx_spreadsheet` → HtmlXlsxConverter / openpyxl from HTML tables or legacy sheets). Do NOT use soffice/LibreOffice or pandoc. Creation only — editing existing files is out of scope."
license: Proprietary. LICENSE.txt has complete terms
---

# XLSX — criação via pipeline HTML (openpyxl)

## Visão geral

A geração canônica de `.xlsx` passa pelo **pipeline HTML** (`create_xlsx_spreadsheet` → `<table>` → `HtmlXlsxConverter` / openpyxl). Aceita HTML/template com tabelas ou o legado `sheets` (abas → HTML). Evite soffice e pandoc.

## Quick Reference

| Tarefa | Abordagem |
|---|---|
| Criar `.xlsx` novo | `create_xlsx_spreadsheet` (HTML table / sheets) |
| Editar `.xlsx` existente | **Fora do escopo.** |
| Recalcular fórmulas | Gravadas como string; o Excel/Sheets calcula ao abrir. |

## Como gerar

HTML com tabela:

```python
result = await create_xlsx_spreadsheet.coroutine({
    "title": "Vendas",
    "html": (
        '<table data-sheet-name="Vendas">'
        "<tr><th>Mês</th><th>Receita</th></tr>"
        "<tr><td>Jan</td><td>12000</td></tr>"
        "</table>"
    ),
})
```

Abas legadas:

```python
from src.models.xlsx_document import XlsxDocumentInput, XlsxSheetInput

payload = XlsxDocumentInput(
    sheets=[
        XlsxSheetInput(
            name="Vendas",
            header=True,
            rows=[
                ["Mês", "Receita", "Custo"],
                ["Jan", 12000, 8000],
                ["Total", "=SUM(B2:B2)", "=SUM(C2:C2)"],
            ],
        ),
    ],
)
result = await create_xlsx_spreadsheet.coroutine(payload)
```

HTML sem tabela utilizável → `{"error": ...}` sem arquivo. Devolve `{path, url, metadata}` com `kind=xlsx` — **use `url`**.

## Limitações (escopo desta versão)

- **Apenas criação** — fora do escopo editar planilha existente.
- Fórmulas não são recalculadas pelo openpyxl.
- Sem gráficos / pivot / formatação condicional rica no caminho HTML.

## Onde o arquivo é salvo

- `backend/outputs/documents/xlsx/<timestamp>.xlsx`
- `GET /api/files/xlsx/<name>`

## Caminhos aposentados (NÃO use)

- soffice / LibreOffice / pandoc
- Scripts legados em `backend/skills/xlsx/scripts/`

## Dependências

- openpyxl (via `HtmlXlsxConverter` no pipeline HTML)
