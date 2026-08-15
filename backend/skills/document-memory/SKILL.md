---
name: document-memory
description: "Use this skill whenever the user wants to persist a WHOLE document, article, webpage, or book for later semantic search — not a short fact. Triggers include: 'salve isso pra buscar depois', 'indexe este documento/livro/página', 'lembre do conteúdo desse PDF', or any request to make a large chunk of text (from a URL, a local .pdf/.docx/.txt/.md file, or text the agent already obtained) searchable in future conversations. Use the tool `ingest_document` to index and `search_documents` to retrieve. Do NOT use `save_memory`/`search_memory` for this — those are for short atomic facts/preferences (capped ~2000 chars) and will reject long content. Do NOT use for documents the user wants CREATED (.docx/.xlsx/.pptx generation) — that's the docx/xlsx/pptx skills."
license: Proprietary. LICENSE.txt has complete terms
---

# Document memory — ingestão com chunking + busca semântica

## Visão geral

Diferente de `save_memory`/`search_memory` (`memory_tools.py` — fatos curtos e
atômicos, ~2000 chars no máximo), esta capability indexa **corpus de texto
inteiros**: uma página, um artigo, um livro. O conteúdo é quebrado em chunks
de ~2000 chars (~500 tokens) com overlap de ~200 chars, e cada chunk vira um
embedding separado (`mxbai-embed-large`, mesma infra do `memory_tools.py`,
namespace **separado**: `("documents", document_id)` em vez de
`("memories",)`).

**Por que chunking, e não trocar de modelo de embedding**: um único embedding
sobre um texto longo dilui o significado inteiro num vetor — a busca semântica
depois não acha nada com precisão. Isso vale mesmo com um modelo de contexto
maior. Chunks pequenos e overlapping é a prática padrão para retrieval
granular, independente do tamanho da janela de contexto do embedder.

## Quick Reference

| Tarefa | Tool |
|---|---|
| Indexar um documento (tenho o texto) | `ingest_document(title, content=texto)` |
| Indexar um arquivo local (.pdf/.docx/.txt/.md) | `ingest_document(title, file_path="outputs/...")` |
| Indexar uma URL | `ingest_document(title, url="https://...")` |
| Buscar em TODOS os documentos indexados | `search_documents(query)` |
| Buscar dentro de UM documento específico | `search_documents(query, document_id=...)` |
| Salvar um fato curto ("usuário prefere X") | **NÃO use esta skill** — use `save_memory` |

## Como usar

Forneça **exatamente uma** fonte para `ingest_document`:

```python
# 1. Texto que o agente já obteve (já leu/raspou em outro passo)
await ingest_document(title="Doc de arquitetura", content=texto_extraido)

# 2. Arquivo local — confinado a outputs/ ou workspace/
await ingest_document(title="Manual do produto", file_path="outputs/uploads/pdf/manual.pdf")

# 3. URL — a tool baixa e extrai o texto visível do HTML
await ingest_document(title="Post do blog", url="https://exemplo.com/artigo")
```

A tool devolve `document_id` (hash determinístico da fonte) e a contagem de
chunks salvos. **Reingerir a MESMA fonte substitui os chunks anteriores** —
não acumula duplicatas.

```python
resultado = await search_documents(query="qual é a política de retenção?", limit=5)
# ou, restrito a um documento:
resultado = await search_documents(query="...", document_id="a1b2c3...")
```

## Formatos de arquivo suportados

`.pdf` (via `pypdf`), `.docx` (via `python-docx`, extração de parágrafos —
sem preservar headings/tabelas), `.txt`, `.md`. Qualquer outra extensão
retorna erro explícito, sem tentativa de parsing.

## Limitações (escopo desta versão)

- Extração de texto simples (texto corrido) — não preserva estrutura
  (headings, tabelas) do documento de origem.
- PDF escaneado (sem camada de texto) extrai string vazia — nenhum OCR.
- Sem limite de tamanho de documento — um livro inteiro é aceito, mas a
  ingestão é sequencial (embeddings em lote via `store.abatch`, ainda assim
  pode levar algum tempo para documentos muito grandes).
- `file_path` confinado a `outputs/` e `workspace/` — nunca o repositório
  inteiro nem caminhos absolutos arbitrários.

## Onde os dados ficam

Postgres/pgvector, mesmo Store do LangGraph configurado em `langgraph.json`
(`store.index`, 1024 dims, `mxbai-embed-large`). Namespace
`("documents", document_id)`, uma chave por chunk (`chunk-00000`, ...).

## Erros comuns

- Nenhuma fonte, ou mais de uma fonte (`content`+`file_path`, etc.) →
  `ERRO: forneça exatamente uma fonte`.
- `file_path` fora de `outputs/`/`workspace/` → `ERRO: acesso negado`.
- Extensão não suportada → `ERRO: Formato não suportado`.
- URL inacessível → `ERRO ao baixar '<url>': <detalhe>`.
