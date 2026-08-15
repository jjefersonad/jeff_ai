---
name: read-document
description: "Use this skill whenever the user wants to READ the contents of an existing document file (.docx, .xlsx, .pptx, .pdf, .html, .csv, .json, .xml, .md, .txt) — to summarize, quote, extract data, or answer questions about it. Triggers include: 'leia esse documento', 'o que diz esse PDF', 'resuma o .docx', 'me mostra a planilha', 'analise esse .pptx', 'qual o conteúdo desse CSV', 'leia esse HTML', or any request to extract text/data from a file the agent does not yet have in context. Use the tool `read_document(path)`. Do NOT use for documents the user wants CREATED (Word/Excel/PPT generation) — that's the `docx`/`xlsx`/`pptx` skills. Do NOT use for INDEXING the document for later semantic search — that's the `document-memory` skill. Do NOT use for short atomic facts/preferences — that's `save_memory`/`search_memory`."
license: Proprietary. LICENSE.txt has complete terms
---

# Read document — extração de texto de arquivos Office, PDF e similares

Esta skill é o caminho oficial para **LER** documentos que o usuário
referencia por path. Diferente das skills irmãs, **não cria** nada — só
extrai texto e devolve em Markdown.

## Quando usar

- O usuário pede para **ler, abrir, resumir, citar, ou analisar** o
  conteúdo de um arquivo `.docx`/`.xlsx`/`.pptx`/`.pdf`/`.html`/`.csv`/
  `.json`/`.xml`/`.md`/`.txt`.
- O usuário cola um path ou nome de arquivo e diz "leia isso" /
  "o que tem aqui" / "extraia X desse arquivo".
- O agente precisa de uma citação literal de dentro de um documento
  armazenado no repositório.

## Quando NÃO usar

| Caso | Use em vez de |
|---|---|
| Criar um .docx/.xlsx/.pptx **novo** | Skill `docx` / `xlsx` / `pptx` |
| Indexar para busca semântica futura | Skill `document-memory` (tool `ingest_document`) |
| Fato/preferência atômica curta | `save_memory` |
| Editar arquivo de código-fonte | Tool `edit_file` / `patch_file` |
| Verificar que o arquivo **existe** | Tool `ls` / `list_project_files` |

## Como usar

A tool `read_document(path, format_hint=None)` aceita:

- `path` — relativo a `REPO_ROOT` (`backend/src/foo.py`, `docs/spec.md`)
  ou absoluto dentro do repo. Path fora do repo é rejeitado.
- `format_hint` — opcional; força o formato se a extensão não for
  confiável. Ex.: `format_hint="pdf"` para um arquivo sem extensão.

Devolve Markdown puro (com header HTML `<!-- read_document: ... -->`).
Tabelas viram texto plano (separadas por `|`). Imagens viram
placeholders `[image: ...]`. **Não preserva formatação rica** —
se o usuário precisa disso, abra o arquivo na UI nativa do Office.

## Fluxo de decisão

1. O usuário pediu para ler um arquivo. Você sabe o path?
   - **Sim** → chame `read_document(path=...)` direto.
   - **Não, mas tem pista** (nome, pasta) → use `list_project_files` /
     `grep_project` para localizar, depois `read_document`.
2. O arquivo é muito grande (>200KB)? A tool trunca com aviso. Se o
   usuário precisa do conteúdo completo, sugira abrir na UI nativa.
3. O path está fora do `REPO_ROOT`? A tool rejeita com mensagem clara.
   Não tente outros paths.

## Limitações conhecidas

- **PDFs escaneados** (sem camada de texto): markitdown pode devolver
  string vazia. Sugira OCR (outra tool, fora do escopo desta skill).
- **Tabelas complexas** (multi-célula com células mescladas): viram
  texto plano. Para análise estrutural, use a UI nativa.
- **Imagens dentro de docs**: viram placeholders, não são extraídas.
  Se a análise visual é o objetivo, use a skill de imagens.
- **Formatos proprietários antigos** (.doc, .xls, .ppt): NÃO suportados.
  Sugira converter para os formatos modernos.

## Histórico

Esta skill substitui a change `document-reading-tools` (que previa
4 readers DDD, abandonada). Decisão registrada em
`backend/src/tools/read_document_tool.py` (docstring do módulo).
