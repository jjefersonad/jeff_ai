---
name: proposal
description: "Use this skill for commercial proposals, quotes, and styled client deliverables that should look polished in the browser before becoming PDF (or Office). Always preview-first: `preview_html_document` with template `proposal`, show the html url for web review, iterate, then finalize with `create_pdf_document` (prefer `from_preview`). Do not jump straight to PDF as the only path."
license: Proprietary. LICENSE.txt has complete terms
---

# Proposta comercial — template + preview-first

## Visão geral

Propostas e documentos comerciais estilizados usam o **template Jinja2 `proposal`** (`backend/templates/documents/proposal/`) e o fluxo **preview HTML no web** antes do arquivo final.

Entregável típico: PDF (`create_pdf_document`, `metadata.kind="pdf"`). Office (`create_docx_document` etc.) só se o usuário pedir explicitamente esse formato.

## Fluxo principal (obrigatório para propostas)

1. **`preview_html_document`** com `template: "proposal"` e `data` preenchido (cliente, seções, preços, etc.).
2. Mostre a **`url`** (`/api/files/html/...`) — o frontend abre preview no navegador.
3. Itere: novo preview se o usuário pedir ajustes.
4. **Finalize** com `create_pdf_document` preferindo **`from_preview`** (url ou filename do HTML).

Não documente “só chame `create_pdf_document` direto” como fluxo principal de proposta. Atalho direto existe para pedidos explícitos (“gera o PDF agora sem preview”), mas não é o default desta skill.

## Exemplo

```python
preview = await preview_html_document.coroutine({
    "template": "proposal",
    "title": "Proposta — Acme",
    "data": {
        "client_name": "Acme Ltda",
        "intro": "...",
        "sections": [{"heading": "Escopo", "body": "..."}],
    },
})
# Resposta ao usuário: link markdown com preview["url"]

final = await create_pdf_document.coroutine({
    "from_preview": preview["url"],
})
# Entregue final["url"] (kind pdf)
```

## Relação com outras skills

- `pdf` — detalhes do pipeline HTML → PDF / WeasyPrint
- `docx` / `xlsx` / `pptx` — só se o usuário pedir esses formatos após (ou em vez de) o PDF

## Limitações

- Criação de artefatos novos; edição de PDF/Office existente fora do escopo.
- Preview HTML é o passo de revisão — não substitua por colar HTML bruto no chat.
