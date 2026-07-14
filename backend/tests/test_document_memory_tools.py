"""Testes de `ingest_document` / `search_documents`.

Usam um `InMemoryStore` do LangGraph e fazem patch de `get_store`, então não
dependem de Postgres, pgvector, Ollama ou de um runtime LangGraph ativo (o
`InMemoryStore` sem embedder configurado faz busca textual simples em vez de
semântica — suficiente para validar o comportamento das tools).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from langgraph.store.memory import InMemoryStore

import src.tools.document_memory_tools as dm


@pytest.fixture
def store(monkeypatch):
    s = InMemoryStore()
    monkeypatch.setattr(dm, "get_store", lambda: s)
    return s


# =========================================================================== #
# Validação de fonte
# =========================================================================== #
async def test_ingest_rejects_no_source(store):
    result = await dm.ingest_document.ainvoke({"title": "x"})
    assert "ERRO" in result


async def test_ingest_rejects_multiple_sources(store):
    result = await dm.ingest_document.ainvoke(
        {"title": "x", "content": "a", "file_path": "outputs/b.txt"}
    )
    assert "ERRO" in result


# =========================================================================== #
# Ingestão via `content` + chunking
# =========================================================================== #
async def test_ingest_content_chunks_long_text(store):
    long_text = "Frase de exemplo sobre Python. " * 300  # bem acima de 2000 chars

    result = await dm.ingest_document.ainvoke(
        {"title": "Sobre Python", "content": long_text}
    )

    assert "indexado" in result
    doc_id = dm._document_id("Sobre Python")
    assert doc_id in result

    items = await store.asearch((dm.DOCUMENTS_NAMESPACE_ROOT, doc_id), limit=1000)
    assert len(items) > 1  # texto longo vira múltiplos chunks
    assert all(item.value["title"] == "Sobre Python" for item in items)
    assert all(item.value["total_chunks"] == len(items) for item in items)


async def test_ingest_short_content_is_single_chunk(store):
    result = await dm.ingest_document.ainvoke(
        {"title": "Fato curto", "content": "Python é uma linguagem de programação."}
    )
    assert "1 chunks salvos" in result


# =========================================================================== #
# Reingestão substitui, não acumula
# =========================================================================== #
async def test_reingest_same_source_replaces_chunks(store):
    await dm.ingest_document.ainvoke({"title": "doc", "content": "versão um. " * 300})
    doc_id = dm._document_id("doc")
    items_v1 = await store.asearch((dm.DOCUMENTS_NAMESPACE_ROOT, doc_id), limit=1000)

    result_v2 = await dm.ingest_document.ainvoke(
        {"title": "doc", "content": "versão dois totalmente diferente. " * 10}
    )

    items_v2 = await store.asearch((dm.DOCUMENTS_NAMESPACE_ROOT, doc_id), limit=1000)
    assert f"substituindo {len(items_v1)} chunks antigos" in result_v2
    assert len(items_v2) != len(items_v1) or all(
        "versão dois" in i.value["content"] for i in items_v2
    )
    assert not any("versão um" in i.value["content"] for i in items_v2)


# =========================================================================== #
# Ingestão via `file_path` — extração + confinamento
# =========================================================================== #
async def test_ingest_txt_file(store, tmp_path, monkeypatch):
    outputs_dir = dm.BACKEND_DIR / "outputs" / "_test_scratch"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    f = outputs_dir / "nota.txt"
    f.write_text("Conteúdo de teste do arquivo txt.", encoding="utf-8")
    try:
        rel_path = str(f.relative_to(dm.BACKEND_DIR))
        result = await dm.ingest_document.ainvoke(
            {"title": "Nota", "file_path": rel_path}
        )
        assert "indexado" in result
        doc_id = dm._document_id(rel_path)
        items = await store.asearch((dm.DOCUMENTS_NAMESPACE_ROOT, doc_id), limit=10)
        assert "Conteúdo de teste" in items[0].value["content"]
    finally:
        f.unlink()
        outputs_dir.rmdir()


async def test_ingest_file_outside_allowed_roots_is_denied(store):
    result = await dm.ingest_document.ainvoke(
        {"title": "x", "file_path": "../../etc/passwd"}
    )
    assert "ERRO" in result
    assert "negado" in result


async def test_ingest_missing_file_is_reported(store):
    result = await dm.ingest_document.ainvoke(
        {"title": "x", "file_path": "outputs/does_not_exist.txt"}
    )
    assert "ERRO" in result
    assert "não encontrado" in result


async def test_ingest_unsupported_extension_is_reported(store, tmp_path):
    outputs_dir = dm.BACKEND_DIR / "outputs" / "_test_scratch2"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    f = outputs_dir / "arquivo.exe"
    f.write_bytes(b"\x00\x01")
    try:
        rel_path = str(f.relative_to(dm.BACKEND_DIR))
        result = await dm.ingest_document.ainvoke({"title": "x", "file_path": rel_path})
        assert "ERRO" in result
        assert "não suportado" in result
    finally:
        f.unlink()
        outputs_dir.rmdir()


# =========================================================================== #
# Ingestão via `url` — fetch + strip de HTML
# =========================================================================== #
def test_html_to_text_strips_script_and_style():
    html = """
    <html><head><style>body{color:red}</style></head>
    <body><script>alert('x')</script><h1>Título</h1><p>Parágrafo real.</p></body></html>
    """
    text = dm._html_to_text(html)
    assert "Título" in text
    assert "Parágrafo real" in text
    assert "alert" not in text
    assert "color:red" not in text


async def test_ingest_url_fetches_and_strips_html(store):
    class _FakeResponse:
        text = "<html><body><p>Conteúdo da página.</p></body></html>"

        def raise_for_status(self) -> None:
            return None

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url):
            return _FakeResponse()

    with patch.object(dm.httpx, "AsyncClient", return_value=_FakeClient()):
        result = await dm.ingest_document.ainvoke(
            {"title": "Página", "url": "https://exemplo.com/artigo"}
        )

    assert "indexado" in result
    doc_id = dm._document_id("https://exemplo.com/artigo")
    items = await store.asearch((dm.DOCUMENTS_NAMESPACE_ROOT, doc_id), limit=10)
    assert "Conteúdo da página" in items[0].value["content"]


# =========================================================================== #
# search_documents
# =========================================================================== #
async def test_search_documents_no_results(store):
    result = await dm.search_documents.ainvoke({"query": "nada indexado ainda"})
    assert "Nenhum trecho relevante encontrado." in result


async def test_search_documents_across_all(store):
    await dm.ingest_document.ainvoke({"title": "doc A", "content": "conteúdo de A"})
    await dm.ingest_document.ainvoke({"title": "doc B", "content": "conteúdo de B"})

    result = await dm.search_documents.ainvoke({"query": "conteúdo", "limit": 10})
    assert "doc A" in result
    assert "doc B" in result


async def test_search_documents_scoped_to_one_document(store):
    await dm.ingest_document.ainvoke({"title": "doc A", "content": "conteúdo de A"})
    await dm.ingest_document.ainvoke({"title": "doc B", "content": "conteúdo de B"})
    doc_id_a = dm._document_id("doc A")

    result = await dm.search_documents.ainvoke(
        {"query": "conteúdo", "limit": 10, "document_id": doc_id_a}
    )
    assert "doc A" in result
    assert "doc B" not in result
