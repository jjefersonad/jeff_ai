---
name: docx
description: "Use this skill whenever the user wants to CREATE a new Word document (.docx). Generation uses the HTML pipeline (`create_docx_document` → HtmlDocxConverter / python-docx). Prefer HTML, template, or title+blocks; for styled proposals consider `preview_html_document` first then finalize. Do NOT use pandoc, soffice/LibreOffice or docx-js/Node. Creation only — editing existing files is out of scope."
license: Proprietary. LICENSE.txt has complete terms
---

# DOCX — criação via pipeline HTML (python-docx)

## Visão geral

A geração canônica de `.docx` passa pelo **pipeline HTML** (`create_docx_document` → HTML semântico → `HtmlDocxConverter` / python-docx). Aceita HTML livre, `template`+`data`, ou `title`+`blocks` (legado → HTML). Evite pandoc, soffice e Node.

Para propostas estilizadas, prefira a skill `proposal` (preview HTML → depois DOCX só se o usuário pedir Word).

## Quick Reference

| Tarefa | Abordagem |
|---|---|
| Criar `.docx` novo | `create_docx_document` (HTML / template / blocks) |
| Preview estilizado antes | `preview_html_document` → depois `create_docx_document` |
| Editar `.docx` existente | **Fora do escopo.** |
| Converter `.doc` → `.docx` | **Fora do escopo.** |

## Como gerar (HTML ou blocks)

HTML direto:

```python
result = await create_docx_document.coroutine({
    "title": "Relatório de Status",
    "html": "<h1>Resumo</h1><p>Este relatório resume...</p>",
})
```

Blocks legado (convertidos para HTML):

```python
from src.models.docx_document import DocxDocumentInput, DocxBlockInput

payload = DocxDocumentInput(
    title="Relatório de Status",
    blocks=[
        DocxBlockInput(type="heading", text="Resumo", level=1),
        DocxBlockInput(type="paragraph", text="Este relatório resume..."),
        DocxBlockInput(type="list", items=["Item A", "Item B"], ordered=False),
        DocxBlockInput(type="table", rows=[
            ["Mês", "Receita"],
            ["Jan", "12000"],
        ], header=True),
    ],
)
result = await create_docx_document.coroutine(payload)
```

`blocks` vazio ou string simples não-JSON → `error`.

### Tabelas: use bloco `table` — NUNCA Markdown

Conteúdo tabular **MUST** ir em `type="table"` com `rows`. **MUST NOT** colocar
sintaxe Markdown (`| col |`) em `paragraph` — a tool rejeita com `{"error": ...}`.

A tool devolve `{path, url, metadata}` com `metadata.kind="docx"`. **Use SEMPRE `url`.**

## Limitações (escopo desta versão)

- **Apenas criação** — abrir/regravar `.docx` existente está fora do escopo.
- Conversão semântica HTML→DOCX (não fidelidade CSS de impressão).
- Sem tracked changes, TOC avançado, export para PDF nesta skill.

## Onde o arquivo é salvo

- `backend/outputs/documents/docx/<timestamp>.docx`
- `GET /api/files/docx/<name>`

## Caminhos aposentados (NÃO use)

- pandoc / soffice / LibreOffice / docx-js
- Scripts em `backend/skills/docx/scripts/office/` (legado)

## Dependências

- python-docx (via `HtmlDocxConverter` no pipeline HTML)
