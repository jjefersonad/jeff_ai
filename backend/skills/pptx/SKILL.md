---
name: pptx
description: "Use this skill any time the user wants to CREATE a new PowerPoint (.pptx). Generation uses the HTML pipeline (`create_pptx_presentation` → HtmlPptxConverter / python-pptx from section.slide / div.slide or legacy slides). Do NOT use soffice, pandoc, or pptxgenjs. Creation only — editing existing files is out of scope."
license: Proprietary. LICENSE.txt has complete terms
---

# PPTX — criação via pipeline HTML (python-pptx)

## Visão geral

A geração canônica de `.pptx` passa pelo **pipeline HTML** (`create_pptx_presentation` → `section.slide` / `div.slide` → `HtmlPptxConverter` / python-pptx). Aceita HTML/template ou slides legados. Evite soffice, pandoc e pptxgenjs.

## Quick Reference

| Tarefa | Abordagem |
|---|---|
| Criar `.pptx` novo | `create_pptx_presentation` (HTML slides / slides[]) |
| Editar `.pptx` existente | **Fora do escopo.** |
| Converter para PDF/imagem | **Fora do escopo.** |

## Como gerar

HTML com slides:

```python
result = await create_pptx_presentation.coroutine({
    "title": "Roadmap",
    "html": (
        '<section class="slide"><h1>Roadmap 2026</h1><p>Time de IA</p></section>'
        '<section class="slide"><h2>Objetivos</h2>'
        "<ul><li>Reduzir latência</li><li>Aumentar cobertura</li></ul></section>"
    ),
})
```

Slides legados:

```python
from src.models.pptx_document import PptxDocumentInput, PptxSlideInput

payload = PptxDocumentInput(
    slides=[
        PptxSlideInput(type="title", title="Roadmap 2026", subtitle="Time de IA"),
        PptxSlideInput(
            type="bullets",
            title="Objetivos",
            bullets=["Reduzir latência", "Aumentar cobertura"],
        ),
    ],
)
result = await create_pptx_presentation.coroutine(payload)
```

HTML sem slides utilizáveis → `{"error": ...}` sem arquivo. Devolve `{path, url, metadata}` com `kind=pptx` — **use `url`**.

## Limitações (escopo desta versão)

- **Apenas criação** — fora do escopo editar apresentação existente.
- Conversão semântica (não pixel-perfect CSS).
- Sem speaker notes / animações / SmartArt no caminho HTML v1.

## Onde o arquivo é salvo

- `backend/outputs/documents/pptx/<timestamp>.pptx`
- `GET /api/files/pptx/<name>`

## Caminhos aposentados (NÃO use)

- soffice / pandoc / pptxgenjs / markitdown
- Scripts legados em `backend/skills/pptx/scripts/`

## Dependências

- python-pptx (via `HtmlPptxConverter` no pipeline HTML)
