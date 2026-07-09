"""Testes da rota `GET /api/files/{kind}/{name}` em `image_server.py`.

Cobrem os critérios de aceitação da task `custom-office-doc-tools-task-serving-1`:
- REQ-003 (docx/xlsx/pptx): a rota serve de `outputs/documents/{kind}/` e retorna
  `Content-Type` correto por extensão + `Content-Disposition: attachment`.
- `kind` restrito a `docx|xlsx|pptx`; path traversal e nomes inválidos são
  rejeitados (400); arquivo ausente → 404.
- A `url` retornada pelas tools resolve para o arquivo correto (round-trip).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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

# O `image_server.py` vive em `backend/` (fora de `src/`) — carregamos via
# importlib para que o `sys.path` do pytest não precise do diretório raiz.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("image_server", _BACKEND_DIR / "image_server.py")
assert _spec is not None  # type narrow para mypy
image_server = importlib.util.module_from_spec(_spec)
sys.modules["image_server"] = image_server
_spec.loader.exec_module(image_server)  # type: ignore[union-attr]


@pytest.fixture
def fake_documents_root(tmp_path: Path, monkeypatch) -> Path:
    """Cria uma raiz temporária com subdiretórios docx/xlsx/pptx e aponta o server para ela."""
    root = tmp_path / "documents"
    (root / "docx").mkdir(parents=True)
    (root / "xlsx").mkdir(parents=True)
    (root / "pptx").mkdir(parents=True)
    monkeypatch.setattr(image_server, "DOCUMENTS_DIR", root)
    return root


@pytest.fixture
def client() -> TestClient:
    """Cliente FastAPI para o `image_server.app` (sem subir o servidor real)."""
    return TestClient(image_server.app)


# --- helper ---------------------------------------------------------------


def _seed(root: Path, kind: str, name: str, content: bytes = b"x") -> str:
    """Cria um arquivo fake no subdiretório de `kind` e retorna o nome."""
    path = root / kind / name
    path.write_bytes(content)
    return name


# --- REQ-003: serve do subdiretório correto com Content-Type ---------------


def test_serve_docx_returns_200_with_correct_content_type(fake_documents_root, client):
    name = _seed(fake_documents_root, "docx", "20260708.docx", b"docx-bytes")
    response = client.get("/api/files/docx/20260708.docx")
    assert response.status_code == 200
    assert (
        response.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert response.headers["content-disposition"] == f'attachment; filename="{name}"'
    assert response.content == b"docx-bytes"


def test_serve_xlsx_returns_200_with_correct_content_type(fake_documents_root, client):
    name = _seed(fake_documents_root, "xlsx", "20260708.xlsx", b"xlsx-bytes")
    response = client.get("/api/files/xlsx/20260708.xlsx")
    assert response.status_code == 200
    assert (
        response.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.headers["content-disposition"] == f'attachment; filename="{name}"'


def test_serve_pptx_returns_200_with_correct_content_type(fake_documents_root, client):
    name = _seed(fake_documents_root, "pptx", "20260708.pptx", b"pptx-bytes")
    response = client.get("/api/files/pptx/20260708.pptx")
    assert response.status_code == 200
    assert (
        response.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    assert response.headers["content-disposition"] == f'attachment; filename="{name}"'


# --- Restrição de `kind` e validação de nome --------------------------------


def test_serve_unknown_kind_returns_400(fake_documents_root, client):
    response = client.get("/api/files/pdf/20260708.pdf")
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid document kind"


def test_serve_invalid_extension_returns_400(fake_documents_root, client):
    """Mesmo com kind válido, extensão não suportada é 400."""
    response = client.get("/api/files/docx/20260708.txt")
    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported document type"


def test_serve_path_traversal_in_filename_returns_400(fake_documents_root, client):
    """`..` no nome do arquivo é rejeitado explicitamente pelo handler."""
    # Sem encoding: o nome é entregue cru ao handler, que detecta "..".
    response = client.get("/api/files/docx/..evil.docx")
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid filename"


def test_serve_backslash_in_filename_returns_400(fake_documents_root, client):
    """Barra invertida no nome do arquivo é rejeitada pelo handler."""
    response = client.get("/api/files/docx/sub\\file.docx")
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid filename"


def test_serve_missing_file_returns_404(fake_documents_root, client):
    response = client.get("/api/files/docx/nao_existe.docx")
    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found"


# --- Round-trip: a URL retornada pelas tools resolve para o arquivo -------


def test_url_returned_by_docx_writer_resolves_to_file(fake_documents_root, client):
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


def test_url_returned_by_xlsx_writer_resolves_to_file(fake_documents_root, client):
    writer = XlsxWriter(output_dir=fake_documents_root / "xlsx", url_prefix="/api/files")
    spec = XlsxSpec(sheets=(Sheet(name="S", rows=(("a",),)),))
    out = writer._write_sync(spec)  # type: ignore[attr-defined]

    response = client.get(out.url)
    assert response.status_code == 200
    assert response.headers["content-type"].endswith("spreadsheetml.sheet")
    assert response.content[:2] == b"PK"  # XLSX é um zip


def test_url_returned_by_pptx_writer_resolves_to_file(fake_documents_root, client):
    writer = PptxWriter(output_dir=fake_documents_root / "pptx", url_prefix="/api/files")
    spec = PptxSpec(slides=(TitleSlide(title="Capa"),))
    out = writer._write_sync(spec)  # type: ignore[attr-defined]

    response = client.get(out.url)
    assert response.status_code == 200
    assert response.headers["content-type"].endswith("presentationml.presentation")
    assert response.content[:2] == b"PK"  # PPTX é um zip
