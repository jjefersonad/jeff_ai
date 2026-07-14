"""Tool `read_document` — leitura de documentos Office e PDF via markitdown.

Substitui a change `document-reading-tools` (que previa 4 readers distintos
em DDD estrito) por uma única tool flat que delega ao `markitdown` da
Microsoft. Decisão de produto registrada em
`.claude/skills/.../option-c` (ver rationale abaixo).

POR QUE MARKITDOWN, NÃO 4 READERS
=================================

1. **Escopo real do uso**: o agente precisa extrair TEXTO de documentos para
   RAG / citação. Não precisa preservar estrutura de tabelas complexa, OCR
   de PDFs escaneados, ou formatação rica — quem quer isso usa a UI nativa
   do Office ou um viewer externo.

2. **Manutenção**: markitdown é OSS mantido pela Microsoft, lida com
   `.docx`, `.xlsx`, `.pptx`, `.pdf`, `.html`, `.csv`, `.json`, `.xml`,
   imagens (via OCR), áudio (via Whisper), YouTube transcripts. Não vamos
   reinventar 4 parsers quando um só resolve 80% dos casos.

3. **Consistência com a arquitetura atual**: o código de CRIAÇÃO de
   documentos (`create_docx_document`, `create_xlsx_spreadsheet`,
   `create_pptx_presentation`) está em `src/tools/`, não em
   `application/use_cases/`. Aplicar DDD só para leitura seria
   inconsistente.

4. **Regra arquitetural**: `skill-or-mcp-never-subagent`. Uma tool + uma
   skill é o padrão; um subagente de leitura seria errado.

O QUE ESTA TOOL FAZ
===================

Aceita um path (relativo a `REPO_ROOT` ou absoluto dentro do repo) e uma
extensão-alvo opcional. Devolve o documento convertido para Markdown.
Erros são devolvidos como string (não exception) — o langchain tools
trata melhor assim.

FUTURO (P2)
===========

Se algum dia for necessário preservar estrutura complexa (tabelas
multi-célula, formatação), abrir uma nova change com readers DDD próprios.
Por enquanto, markitdown basta.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool
from markitdown import MarkItDown

from src.tools.self_extension import REPO_ROOT, _MAX_READ_CHARS, _within_repo

_log = logging.getLogger(__name__)

# Extensões suportadas pelo markitdown (subset do que ele lida, restrito
# aos formatos de documento mais comuns). Adicionar mais aqui é trivial,
# mas é preciso instalar a dependência extra correspondente.
_SUPPORTED_EXTS: frozenset[str] = frozenset({
    "docx", "xlsx", "pptx", "pdf",
    "html", "htm", "csv", "json", "xml",
    "md", "markdown", "txt",
})

# Limite duro de saída (caracteres). markitdown devolve markdown — pode
# ficar grande. Cortamos com aviso para não estourar o context do modelo.
_OUTPUT_MAX_CHARS: int = _MAX_READ_CHARS  # 200KB, mesmo limite do read_project_file


def _resolve(path: str) -> Path | str:
    """Resolve `path` para um `Path` absoluto DENTRO do repo, ou devolve
    uma string de erro se estiver fora / não existir / não for arquivo.
    """
    if not path or not path.strip():
        return "Caminho vazio."
    p = Path(path)
    if not p.is_absolute():
        p = REPO_ROOT / path
    try:
        p = p.resolve()
    except OSError as e:
        return f"Caminho inválido: {e}"
    if not _within_repo(p):
        return "Acesso negado: caminho fora do repositório."
    if not p.exists():
        return f"Arquivo não encontrado: {path}"
    if not p.is_file():
        return f"Não é um arquivo: {path}"
    return p


def _detect_format(path: Path) -> str:
    """Detecta o formato pela extensão. Devolve string lowercase sem dot."""
    ext = path.suffix.lower().lstrip(".")
    return ext


def _truncate(text: str) -> str:
    if len(text) <= _OUTPUT_MAX_CHARS:
        return text
    return (
        text[:_OUTPUT_MAX_CHARS]
        + f"\n\n[...truncado em {_OUTPUT_MAX_CHARS} caracteres. "
        "Use a UI nativa do Office / um viewer para o documento completo.]"
    )


@tool
def read_document(
    path: str,
    format_hint: Optional[str] = None,
) -> str:
    """Lê um documento (Office, PDF, HTML, CSV, JSON, etc.) e devolve em Markdown.

    `path` é relativo a `REPO_ROOT` ou absoluto dentro do repositório.
    Suporta `.docx`, `.xlsx`, `.pptx`, `.pdf`, `.html`, `.csv`, `.json`,
    `.xml`, `.md`, `.txt`. O conteúdo é convertido para Markdown — útil
    para RAG, citação, e análise textual. **Não preserva formatação
    complexa** (tabelas viram texto, imagens viram placeholders).

    `format_hint` é opcional; se passado, força o formato (ex.: `"pdf"`).
    Útil quando o arquivo não tem extensão confiável.

    Path fora do repositório é rejeitado. Arquivos grandes são truncados
    em ~200KB. Erros de parsing são devolvidos como string (não exception).
    """
    resolved = _resolve(path)
    if isinstance(resolved, str):
        return resolved  # mensagem de erro
    p: Path = resolved

    fmt = (format_hint or _detect_format(p)).lower().lstrip(".")
    if fmt not in _SUPPORTED_EXTS:
        return (
            f"Formato não suportado: .{fmt}. "
            f"Suportados: {', '.join(sorted(_SUPPORTED_EXTS))}."
        )

    try:
        md = MarkItDown()
        result = md.convert(str(p))
    except Exception as e:  # markitdown levanta exceções genéricas; capturamos tudo
        _log.warning("markitdown falhou para %s: %s", p, e)
        return f"Erro ao ler '{path}': {e}"

    text = result.text_content or ""
    if not text.strip():
        return f"Documento '{path}' está vazio ou não tem texto extraível."

    header = (
        f"<!-- read_document: {p.relative_to(REPO_ROOT)} ({len(text)} chars) -->\n"
    )
    return _truncate(header + text)
