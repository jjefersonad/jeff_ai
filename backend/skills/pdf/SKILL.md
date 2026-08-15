---
name: pdf
description: "Use this skill whenever the user wants to CREATE a new PDF (.pdf), especially styled reports or proposals. Prefer preview-first: call `preview_html_document` (HTML/CSS or template), show the url for web review, then `create_pdf_document` (WeasyPrint via HTML pipeline) — ideally with `from_preview`. Do NOT present fpdf2, pandoc, or soffice as the agent API. Creation only — editing/merge/OCR of existing PDFs is out of scope. For Word/Excel/PowerPoint use those skills."
license: Proprietary. LICENSE.txt has complete terms
---

# PDF — criação via pipeline HTML/CSS (WeasyPrint)

## Visão geral

A geração canônica de `.pdf` passa pelo **pipeline HTML/CSS** (`RenderHtmlDocument` + WeasyPrint), exposto como `create_pdf_document`. Entrada unificada: HTML livre, `template`+`data`, ou `title`+`blocks` (legado → HTML). **Não** instrua fpdf2, pandoc ou LibreOffice como caminho do agente.

Para propostas e documentos estilizados, veja também a skill `proposal` e o fluxo **preview-first** abaixo.

## Quick Reference

| Tarefa | Abordagem |
|---|---|
| Preview no web (propostas/estilizados) | `preview_html_document` → mostrar `url` |
| PDF final | `create_pdf_document` (HTML/template/`from_preview`) |
| Editar PDF existente | **Fora do escopo.** |
| Merge / OCR / fillable forms | **Fora do escopo.** |

## Preview-first (recomendado)

1. Chame `preview_html_document` com `template`/`html`/`blocks`.
2. Responda com a `url` (`/api/files/html/...`) para o usuário revisar no web.
3. Ajuste com novo preview se pedido.
4. Só então `create_pdf_document` com `from_preview` (filename ou url do HTML) **ou** o mesmo payload.

Não trate “chame `create_pdf_document` direto” como o único fluxo para propostas.

## Como gerar (HTML / template)

```python
# Preferido para propostas
preview = await preview_html_document.coroutine({
    "template": "proposal",
    "data": {"client": "...", "sections": [...]},
    "title": "Proposta Comercial",
})
# mostre preview["url"] ao usuário

pdf = await create_pdf_document.coroutine({
    "from_preview": preview["url"],  # ou o filename .html
})
```

HTML direto:

```python
result = await create_pdf_document.coroutine({
    "title": "Relatório",
    "html": "<h1>Resumo</h1><p>Texto...</p>",
    "css": "h1 { color: #222; }",
})
```

`blocks` legado ainda funciona (convertido para HTML). String simples não-JSON → `error`.

A tool devolve `{path, url, metadata}` com `metadata.kind="pdf"`. **Use SEMPRE `url`** no markdown.

## Contrato de retorno

```json
{
  "path": "/app/backend/outputs/documents/pdf/20260807120000123456.pdf",
  "url":  "http://localhost:3000/api/files/pdf/20260807120000123456.pdf",
  "metadata": {"kind": "pdf", "title": "Relatório"}
}
```

## Limitações (escopo desta versão)

- **Apenas criação** — edição de PDF existente não é suportada (fora do escopo).
- Sem merge/split, OCR, formulários fillable ou assinatura digital.
- Motor de render: WeasyPrint (HTML/CSS); não use fpdf2 como API.

## Onde o arquivo é salvo

- `backend/outputs/documents/pdf/<timestamp>.pdf`
- Servido em `GET /api/files/pdf/<name>`

## Caminhos aposentados (NÃO use)

- fpdf2 como API do agente
- pandoc / soffice / LibreOffice
- Gerar docx e pedir conversão manual — use `create_pdf_document` / preview

## Dependências

- WeasyPrint (pipeline HTML → PDF)
- Templates em `backend/templates/documents/` (ex.: `proposal`)
