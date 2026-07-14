"""Memória de DOCUMENTOS: ingestão com chunking + busca semântica granular.

Diferente de `memory_tools.py` (fatos atômicos curtos, ~1000 chars), este
módulo indexa CORPUS DE TEXTO inteiros — de uma página a um livro. Um único
embedding sobre um texto longo dilui o significado e piora a busca; a solução
é quebrar o conteúdo em chunks e embedar cada um separadamente. O tamanho do
chunk importa mais para a qualidade do retrieval do que a janela de contexto
do modelo de embedding — por isso continuamos usando `mxbai-embed-large`
(`src/models/ollama_embeddings.py`), já configurado no `langgraph.json`, em
vez de trocar por um modelo com contexto maior.

O tamanho do chunk (`_CHUNK_SIZE`) é CALIBRADO EMPIRICAMENTE contra o
`mxbai-embed-large` local, não estimado por "~4 chars/token": testado
diretamente via `ollama_embeddings.embed_documents` com texto em português,
1400 chars passa, 1500 já falha com "input length exceeds the context
length" — português tokeniza pior que a heurística assume (acentuação,
subword splitting). Separadamente, o TAMANHO DO LOTE de embedding também é
limitado — não pelo modelo, mas pelo proxy Cloudflare na frente do Ollama
self-hosted, que derruba requisições demoradas com 524 antes de chegar no
servidor. Ver `_EMBED_BATCH_SIZE` abaixo.

Namespace `("documents", document_id)` — SEPARADO de `("memories",)` de
`memory_tools.py`. Corpus de documentos e fatos atômicos não devem se
misturar na mesma busca semântica.

`document_id` é determinístico (hash da fonte: url, file_path, ou title
quando o conteúdo já vem pronto) — reingerir a MESMA fonte SUBSTITUI os
chunks anteriores em vez de acumular duplicatas no índice.
"""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
from pathlib import Path

import httpx
from docx import Document as DocxDocument
from langchain_core.tools import tool
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.config import get_store
from langgraph.store.base import BaseStore, PutOp
from pypdf import PdfReader

_THIS = Path(__file__).resolve()
BACKEND_DIR = _THIS.parents[2]
# Leitura de `file_path` confinada aos mesmos diretórios servidos pelo backend
# (outputs/ e workspace/) — nunca o repositório inteiro. Mesma disciplina do
# `document-serving-spec` (change `document-reading-tools`, ainda não
# implementada) para as rotas HTTP de documentos enviados.
_ALLOWED_ROOTS = (BACKEND_DIR / "outputs", BACKEND_DIR / "workspace")

DOCUMENTS_NAMESPACE_ROOT = "documents"

# Tamanho por chunk: calibrado empiricamente contra `mxbai-embed-large` local
# com texto em português (ver docstring do módulo) — 1400 chars passa, 1500
# falha. 1000 dá margem segura, e casa com `MAX_MEMORY_CHARS` de
# `memory_tools.py` (mesma calibração, mesmo modelo). Overlap de ~100 chars
# preserva contexto entre chunks vizinhos sem cortar uma ideia bem no meio.
_CHUNK_SIZE = 1000
_CHUNK_OVERLAP = 100

# `store.abatch(ops)` embeda TODOS os chunks do lote numa ÚNICA chamada HTTP
# ao Ollama (`aembed_documents` recebe a lista inteira de textos de uma vez).
# Calibrado empiricamente: 20 chunks de ~1000 chars num lote só passa; 50
# chunks estoura o timeout do proxy Cloudflare na frente do Ollama self-hosted
# (erro 524 — "a origem demorou demais", não um erro de conteúdo). Para um
# livro inteiro (centenas de chunks), o `abatch` precisa ser fatiado em lotes
# pequenos e sequenciais — ver `_BATCH_SIZE` em `ingest_document`.
_EMBED_BATCH_SIZE = 15

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=_CHUNK_SIZE,
    chunk_overlap=_CHUNK_OVERLAP,
)


# --------------------------------------------------------------------------- #
# Extração de texto por fonte
# --------------------------------------------------------------------------- #
class _TextExtractingHTMLParser(HTMLParser):
    """Extrai o texto visível de um HTML, descartando script/style/etc."""

    _SKIP_TAGS = {"script", "style", "noscript", "template"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self._parts.append(text)

    def get_text(self) -> str:
        return "\n".join(self._parts)


def _html_to_text(html: str) -> str:
    parser = _TextExtractingHTMLParser()
    parser.feed(html)
    return parser.get_text()


def _within_allowed_roots(path: Path) -> bool:
    return any(path == root or root in path.parents for root in _ALLOWED_ROOTS)


def _extract_text_from_file(path: Path) -> str:
    """Extrai texto de `.pdf`, `.docx`, `.txt` ou `.md`.

    Extração simples e direta (não estruturada — sem preservar headings ou
    tabelas). Se a change `document-reading-tools` (specs em draft) entregar
    readers estruturados (`DocxReader`/`PdfReader` sobre `DocumentContent`),
    esta função pode passar a delegar a eles para chunking que respeita
    fronteiras de seção. Por ora, texto corrido é suficiente para indexação.
    """
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        doc = DocxDocument(str(path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="ignore")
    raise ValueError(
        f"Formato não suportado: '{suffix}'. Use .pdf, .docx, .txt ou .md."
    )


def _document_id(source_key: str) -> str:
    """Hash determinístico da fonte — mesma fonte, mesmo `document_id`."""
    return hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:16]


async def _delete_existing_chunks(store: BaseStore, document_id: str) -> int:
    """Apaga todos os chunks existentes de `document_id` (política de substituição).

    Drena a namespace em lotes: busca (sem query = listagem) até esvaziar,
    deletando cada chave encontrada. Necessário para não acumular chunks
    duplicados quando a mesma fonte é reingerida.
    """
    namespace = (DOCUMENTS_NAMESPACE_ROOT, document_id)
    deleted = 0
    while True:
        items = await store.asearch(namespace, limit=100)
        if not items:
            break
        for item in items:
            await store.adelete(namespace, item.key)
            deleted += 1
        if len(items) < 100:
            break
    return deleted


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@tool
async def ingest_document(
    title: str,
    content: str | None = None,
    file_path: str | None = None,
    url: str | None = None,
) -> str:
    """Indexa um documento inteiro (página, artigo, livro) para busca semântica futura.

    Diferente de `save_memory` (fatos curtos e atômicos), esta tool é para
    CORPUS de texto: o conteúdo é quebrado em chunks e cada um vira um
    embedding separado, permitindo recuperar trechos relevantes depois via
    `search_documents`.

    Forneça EXATAMENTE UMA fonte:
    - `content`: texto que você já obteve (já leu um arquivo, já raspou uma
      página com outra tool).
    - `file_path`: caminho de um arquivo local em outputs/ ou workspace/
      (.pdf, .docx, .txt, .md) — esta tool extrai o texto.
    - `url`: uma URL — esta tool baixa e extrai o texto visível do HTML.

    Reingerir a MESMA fonte (mesmo `file_path`/`url`, ou mesmo `title` quando
    a fonte é `content` bruto) SUBSTITUI os chunks anteriores — não acumula
    duplicatas no índice.
    """
    provided = [v for v in (content, file_path, url) if v]
    if len(provided) != 1:
        return "ERRO: forneça exatamente uma fonte: content, file_path OU url (não mais de uma, nem nenhuma)."

    if url:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except httpx.HTTPError as e:
            return f"ERRO ao baixar '{url}': {e}"
        text = _html_to_text(resp.text)
        source_key = url
    elif file_path:
        path = (BACKEND_DIR / file_path).resolve()
        if not _within_allowed_roots(path):
            return "ERRO: acesso negado — file_path deve estar em outputs/ ou workspace/."
        if not path.is_file():
            return f"ERRO: arquivo não encontrado: {file_path}"
        try:
            text = _extract_text_from_file(path)
        except Exception as e:
            return f"ERRO ao ler '{file_path}': {e}"
        source_key = file_path
    else:
        text = content or ""
        source_key = title

    text = text.strip()
    if not text:
        return "ERRO: nenhum texto extraído da fonte fornecida."

    chunks = _splitter.split_text(text)
    if not chunks:
        return "ERRO: não foi possível dividir o texto em chunks."

    document_id = _document_id(source_key)
    store = get_store()

    deleted = await _delete_existing_chunks(store, document_id)

    namespace = (DOCUMENTS_NAMESPACE_ROOT, document_id)
    ops = [
        PutOp(
            namespace=namespace,
            key=f"chunk-{i:05d}",
            value={
                "content": chunk,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "title": title,
                "source": source_key,
            },
        )
        for i, chunk in enumerate(chunks)
    ]
    # Fatiado em lotes pequenos (`_EMBED_BATCH_SIZE`) — um `abatch` só com
    # centenas de chunks estoura o timeout do proxy na frente do Ollama
    # self-hosted (ver comentário de `_EMBED_BATCH_SIZE`).
    for start in range(0, len(ops), _EMBED_BATCH_SIZE):
        await store.abatch(ops[start : start + _EMBED_BATCH_SIZE])

    replaced_note = f" (substituindo {deleted} chunks antigos)" if deleted else ""
    return (
        f"Documento '{title}' indexado: {len(chunks)} chunks salvos{replaced_note}. "
        f"document_id={document_id}"
    )


@tool
async def search_documents(
    query: str, limit: int = 5, document_id: str | None = None
) -> str:
    """Busca semântica em documentos indexados por `ingest_document`.

    Use quando precisar recuperar trechos de um documento (página, livro,
    artigo) indexado anteriormente. Passe `document_id` (devolvido por
    `ingest_document`) para restringir a busca a um único documento; omita
    para buscar em TODOS os documentos indexados.
    """
    store = get_store()
    namespace = (
        (DOCUMENTS_NAMESPACE_ROOT, document_id)
        if document_id
        else (DOCUMENTS_NAMESPACE_ROOT,)
    )
    results = await store.asearch(namespace, query=query, limit=limit)
    if not results:
        return "Nenhum trecho relevante encontrado."

    parts = []
    for item in results:
        v = item.value
        parts.append(
            f"[{v.get('title', '?')} — chunk {v.get('chunk_index', '?')}/"
            f"{v.get('total_chunks', '?')} — document_id={item.namespace[-1]}]\n"
            f"{v.get('content', '')}"
        )
    return "\n\n---\n\n".join(parts)
