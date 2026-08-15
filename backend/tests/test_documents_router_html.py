"""Testes do novo `kind='html'` em `documents_router` (change architecture-diagram).

Skill `architecture-diagram` (backend/skills/architecture-diagram/SKILL.md) escreve
ficheiros `.html` autocontidos em `backend/outputs/documents/html/<timestamp>-<slug>.html`
e devolve `/api/files/html/<file>` no markdown. Estes testes cobrem essa rota sem
depender de `webapp.app` (que tem collection errors pré-existentes em
`mcp_admin_api.py:266` — fora do escopo deste fix).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.infrastructure.web.documents_router as documents_router
from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.users import User


_FAKE_ADMIN = User(
    id="u-1",
    username="admin",
    password_hash="x",
    role="admin",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
)


@pytest.fixture
def html_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Apon DOCUMENTS_DIR para tmp_path/html e cria um ficheiro de teste."""
    monkeypatch.setattr(documents_router, "DOCUMENTS_DIR", tmp_path)
    target = tmp_path / "html"
    target.mkdir()
    return target


@pytest.fixture
def fastapi_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """App FastAPI standalone com a router documents + override de auth.

    Note: nome `fastapi_app` (e não `app`) para evitar colisão com o
    fixture `app` do plugin `pytest-flask`, que tenta patchar
    `response_class` em qualquer fixture chamado `app`.
    """

    async def _fake_user() -> User:
        return _FAKE_ADMIN

    app = FastAPI()
    app.include_router(documents_router.router)
    app.dependency_overrides[require_auth] = _fake_user
    return app


@pytest.fixture
def client(fastapi_app: FastAPI) -> TestClient:
    return TestClient(fastapi_app)


# ---------------------------------------------------------------------------
# Cobre REQ-001: `html` é kind válido; ficheiro .html é servido com text/html
# inline (sem Content-Disposition: attachment) + X-Content-Type-Options: nosniff
# ---------------------------------------------------------------------------


def test_html_is_in_document_kinds() -> None:
    """`_DOCUMENT_KINDS` deve incluir `html` (não mais só docx/xlsx/pptx)."""
    assert "html" in documents_router._DOCUMENT_KINDS


def test_html_has_text_html_media_type() -> None:
    """`text/html` deve estar mapeado para a extensão `.html`."""
    assert documents_router._DOCUMENT_MEDIA_TYPES[".html"] == "text/html"


def test_html_is_not_in_attachment_kinds() -> None:
    """HTML NÃO deve ter Content-Disposition: attachment — o user quer ABRIR
    o diagrama no browser, não baixá-lo."""
    assert "html" not in documents_router._ATTACHMENT_KINDS


def test_html_kind_dir_resolves(html_dir: Path) -> None:
    """`_document_kind_dir('html')` deve devolver `DOCUMENTS_DIR/html`."""
    result = documents_router._document_kind_dir("html")
    assert result == html_dir


def test_serve_html_file_inline(
    html_dir: Path, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REQ-ADD-010 / serving-inline unit-1: HTML autorizado → text/html + inline."""

    target = html_dir / "test-diagram.html"
    target.write_text("<!DOCTYPE html><html><body>diagram</body></html>", encoding="utf-8")

    # Stub de authorization — sem isso, o user não é dono do ficheiro e recebe 404.
    monkeypatch.setattr(
        documents_router, "is_authorized", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        documents_router, "get_file_owner", AsyncMock(return_value=None)
    )

    response = client.get("/api/files/html/test-diagram.html")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    # Defesa em profundidade: nosniff impede MIME-sniffing do browser.
    assert response.headers["x-content-type-options"] == "nosniff"
    disposition = response.headers.get("content-disposition", "")
    assert disposition.startswith("inline")
    assert "attachment" not in disposition
    assert 'filename="test-diagram.html"' in disposition
    assert b"diagram" in response.content


def test_serve_html_unauthorized_returns_opaque_404(
    html_dir: Path, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REQ-ADD-010 / serving-inline unit-2: HTML sem ownership → 404 opaco."""
    target = html_dir / "secret.html"
    target.write_text("<html><body>secret-preview</body></html>", encoding="utf-8")
    monkeypatch.setattr(
        documents_router, "is_authorized", AsyncMock(return_value=False)
    )

    response = client.get("/api/files/html/secret.html")

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found"
    assert b"secret-preview" not in response.content


def test_serve_docx_still_has_attachment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REQ-004 / serving-inline unit-2: Office docs continuam attachment.

    Usa um app standalone idêntico ao fixture `app` para evitar importar
    `webapp` (que tem collection error pré-existente em `mcp_admin_api.py:266`).
    """
    docx_dir = tmp_path / "docx"
    docx_dir.mkdir()
    target = docx_dir / "report.docx"
    target.write_bytes(b"fake-docx-bytes")

    monkeypatch.setattr(documents_router, "DOCUMENTS_DIR", tmp_path)
    monkeypatch.setattr(documents_router, "is_authorized", AsyncMock(return_value=True))
    monkeypatch.setattr(documents_router, "get_file_owner", AsyncMock(return_value=None))

    app = FastAPI()
    app.include_router(documents_router.router)

    async def _fake_user() -> User:
        return _FAKE_ADMIN

    app.dependency_overrides[require_auth] = _fake_user

    response = TestClient(app).get("/api/files/docx/report.docx")

    assert response.status_code == 200
    # Office docs: download forçado.
    assert "attachment" in response.headers.get("content-disposition", "")
    assert "nosniff" in response.headers.get("x-content-type-options", "")


def test_unknown_kind_still_returns_400(client: TestClient) -> None:
    """Não-regressão: `kind` inválido continua a retornar 400."""
    response = client.get("/api/files/png/anything.png")
    assert response.status_code == 400


def test_path_traversal_blocked_for_html(
    html_dir: Path, client: TestClient
) -> None:
    """Não-regressão: path traversal bloqueado mesmo com kind=html."""
    response = client.get("/api/files/html/..%2F..%2Fetc%2Fpasswd")
    # O FastAPI normaliza o `..` antes de chegar ao handler → 400 ou 404.
    assert response.status_code in (400, 404)


def test_html_with_unsupported_extension_is_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uma extensão não listada em `_DOCUMENT_MEDIA_TYPES` é rejeitada com 400.

    Cobre a interseção kind/extension: o roteador usa a extensão do ficheiro
    para decidir o mime — uma extensão não-mapeada (ex: `.exe`) é rejeitada
    antes de qualquer leitura.
    """
    monkeypatch.setattr(
        documents_router, "is_authorized", AsyncMock(return_value=True)
    )

    response = client.get("/api/files/html/something.exe")
    # 400 porque `.exe` não está em `_DOCUMENT_MEDIA_TYPES`.
    assert response.status_code == 400
