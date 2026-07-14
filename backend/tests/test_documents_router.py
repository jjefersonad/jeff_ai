"""Testes de `documents_router` (change `consolidate-http-routes-langgraph`).

Substitui o antigo `test_image_server_documents.py` (que testava a mesma
rota em `backend/image_server.py`, antes da migração para o `http.app` do
backend LangGraph). O módulo sendo testado agora é
`src.infrastructure.web.documents_router`, e o `app` que o expõe vem de
`src.infrastructure.web.webapp`. Apontamos `DOCUMENTS_DIR` para `tmp_path`
via `monkeypatch` para nunca tocar em `backend/outputs/documents/` real.
Há também um teste do override por env var para validar o caminho de
configuração documentado em `documents_router.py:17`.

Cobre REQ-002 (custom-http-app) da change `consolidate-http-routes-langgraph`:
- `GET /api/files/{kind}/{filename}` retorna 200 com `Content-Type` e
  `Content-Disposition: attachment` corretos para `kind` em {docx, xlsx, pptx}.
- `kind` inválido → 400; arquivo inexistente → 404; path traversal →
  bloqueado.
- A `url` retornada pelas tools resolve para o arquivo correto (round-trip
  DocxWriter / XlsxWriter / PptxWriter).
- `DOCUMENTS_DIR` é configurável por env var (compatibilidade com o
  padrão usado em `image_server.py`, hoje preservado pelo
  `monkeypatch.setattr`).
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.infrastructure.web.documents_router as documents_router
import src.infrastructure.web.webapp as webapp
from src.domain.documents import (
    DocxSpec,
    Paragraph,
    PptxSpec,
    Sheet,
    TitleSlide,
    XlsxSpec,
)
from src.infrastructure.documents.docx_writer import DocxWriter
from src.infrastructure.documents.pptx_writer import PptxWriter
from src.infrastructure.documents.xlsx_writer import XlsxWriter


@pytest.fixture
def fake_documents_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Cria uma raiz temporária com subdiretórios docx/xlsx/pptx e aponta o
    router para ela via `monkeypatch` em `documents_router.DOCUMENTS_DIR`.

    `DOCUMENTS_DIR` é lido de `os.environ` no momento do `import` do módulo;
    no entando as funções o lêem do ATRIBUTO de módulo (`documents_router.
    DOCUMENTS_DIR`), portanto substituir o atributo no módulo em runtime é
    suficiente para o teste.
    """
    root = tmp_path / "documents"
    (root / "docx").mkdir(parents=True)
    (root / "xlsx").mkdir(parents=True)
    (root / "pptx").mkdir(parents=True)
    monkeypatch.setattr(documents_router, "DOCUMENTS_DIR", root)
    return root


@pytest.fixture
def client() -> TestClient:
    """Cliente FastAPI para o `webapp.app` (sem subir o servidor real)."""
    return TestClient(webapp.app)


# --- helper ---------------------------------------------------------------


def _seed(root: Path, kind: str, name: str, content: bytes = b"x") -> str:
    """Cria um arquivo fake no subdiretório de `kind` e retorna o nome."""
    path = root / kind / name
    path.write_bytes(content)
    return name


# --- REQ-002: serve do subdiretório correto com Content-Type --------------


def test_serve_docx_returns_200_with_correct_content_type(
    fake_documents_root: Path, client: TestClient
):
    name = _seed(fake_documents_root, "docx", "20260708.docx", b"docx-bytes")
    response = client.get("/api/files/docx/20260708.docx")
    assert response.status_code == 200
    assert (
        response.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert response.headers["content-disposition"] == f'attachment; filename="{name}"'
    assert response.content == b"docx-bytes"


def test_serve_xlsx_returns_200_with_correct_content_type(
    fake_documents_root: Path, client: TestClient
):
    name = _seed(fake_documents_root, "xlsx", "20260708.xlsx", b"xlsx-bytes")
    response = client.get("/api/files/xlsx/20260708.xlsx")
    assert response.status_code == 200
    assert (
        response.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.headers["content-disposition"] == f'attachment; filename="{name}"'
    assert response.content == b"xlsx-bytes"


def test_serve_pptx_returns_200_with_correct_content_type(
    fake_documents_root: Path, client: TestClient
):
    name = _seed(fake_documents_root, "pptx", "20260708.pptx", b"pptx-bytes")
    response = client.get("/api/files/pptx/20260708.pptx")
    assert response.status_code == 200
    assert (
        response.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    assert response.headers["content-disposition"] == f'attachment; filename="{name}"'
    assert response.content == b"pptx-bytes"


# --- Restrição de `kind` e validação de nome ------------------------------


def test_serve_unknown_kind_returns_400(
    fake_documents_root: Path, client: TestClient
):
    response = client.get("/api/files/pdf/20260708.pdf")
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid document kind"


def test_serve_invalid_extension_returns_400(
    fake_documents_root: Path, client: TestClient
):
    """Mesmo com kind válido, extensão não suportada é 400."""
    response = client.get("/api/files/docx/20260708.txt")
    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported document type"


def test_serve_path_traversal_in_filename_returns_400(
    fake_documents_root: Path, client: TestClient
):
    """`..` no nome do arquivo é rejeitado explicitamente pelo handler."""
    # Sem encoding: o nome é entregue cru ao handler, que detecta "..".
    response = client.get("/api/files/docx/..evil.docx")
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid filename"


def test_serve_backslash_in_filename_returns_400(
    fake_documents_root: Path, client: TestClient
):
    """Barra invertida no nome do arquivo é rejeitada pelo handler."""
    response = client.get("/api/files/docx/sub\\file.docx")
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid filename"


def test_serve_missing_file_returns_404(
    fake_documents_root: Path, client: TestClient
):
    response = client.get("/api/files/docx/nao_existe.docx")
    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found"


# --- Round-trip: a URL retornada pelas tools resolve para o arquivo -------


def test_url_returned_by_docx_writer_resolves_to_file(
    fake_documents_root: Path, client: TestClient
):
    """A URL `/api/files/docx/<name>` retornada pelo DocxWriter baixa o arquivo certo."""
    writer = DocxWriter(output_dir=fake_documents_root / "docx", url_prefix="/api/files")
    spec = DocxSpec(title="Round-trip", blocks=(Paragraph(text="oi"),))
    # write() é async — disparamos diretamente via _write_sync.
    out = writer._write_sync(spec)  # type: ignore[attr-defined]
    assert out.url.startswith("/api/files/docx/")

    response = client.get(out.url)
    assert response.status_code == 200
    assert response.headers["content-disposition"].endswith(out.url.split("/")[-1] + '"')
    # E o conteúdo é um zip/docx válido (magic bytes "PK").
    assert response.content[:2] == b"PK"


def test_url_returned_by_xlsx_writer_resolves_to_file(
    fake_documents_root: Path, client: TestClient
):
    writer = XlsxWriter(output_dir=fake_documents_root / "xlsx", url_prefix="/api/files")
    spec = XlsxSpec(sheets=(Sheet(name="S", rows=(("a",),)),))
    out = writer._write_sync(spec)  # type: ignore[attr-defined]

    response = client.get(out.url)
    assert response.status_code == 200
    assert response.headers["content-type"].endswith("spreadsheetml.sheet")
    assert response.content[:2] == b"PK"  # XLSX é um zip


def test_url_returned_by_pptx_writer_resolves_to_file(
    fake_documents_root: Path, client: TestClient
):
    writer = PptxWriter(output_dir=fake_documents_root / "pptx", url_prefix="/api/files")
    spec = PptxSpec(slides=(TitleSlide(title="Capa"),))
    out = writer._write_sync(spec)  # type: ignore[attr-defined]

    response = client.get(out.url)
    assert response.status_code == 200
    assert response.headers["content-type"].endswith("presentationml.presentation")
    assert response.content[:2] == b"PK"  # PPTX é um zip


# --- DOCUMENTS_DIR via env var override ----------------------------------


def test_documents_dir_override_via_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """REQ-002: `DOCUMENTS_DIR` é configurável por env var (mesmo padrão
    usado pelo `image_server.py` original e pelos `docker-compose.yml`).

    Reimporta o módulo com a env var setada para validar o caminho
    documentado em `documents_router.py:17`:
    `Path(os.environ.get("DOCUMENTS_DIR", "/deps/backend/outputs/documents"))`.
    """
    root = tmp_path / "documents"
    (root / "docx").mkdir(parents=True)
    (root / "xlsx").mkdir(parents=True)
    (root / "pptx").mkdir(parents=True)
    name = "via_env.docx"
    (root / "docx" / name).write_bytes(b"from-env")

    monkeypatch.setenv("DOCUMENTS_DIR", str(root))
    reloaded = importlib.reload(documents_router)
    try:
        assert reloaded.DOCUMENTS_DIR == root
        # Cliente novo para garantir que o módulo recarregado está montado.
        c = TestClient(webapp.app)
        resp = c.get(f"/api/files/docx/{name}")
        assert resp.status_code == 200
        assert resp.content == b"from-env"
    finally:
        # Restaura o módulo ao estado original (default) para não vazar
        # o tmp_path em outros testes que importem `documents_router`.
        monkeypatch.delenv("DOCUMENTS_DIR", raising=False)
        importlib.reload(documents_router)
