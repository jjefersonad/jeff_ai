"""Testes de `images_router` (change `consolidate-http-routes-langgraph`).

Portado/adaptado de `test_image_server.py` (que testava as mesmas rotas em
`backend/image_server.py`, antes da migração para o `http.app` do backend
LangGraph). O módulo sendo testado agora é `src.infrastructure.web.images_router`,
e o `app` que o expõe vem de `src.infrastructure.web.webapp`. Apontamos
`IMAGES_DIR`/`REFERENCES_DIR` para `tmp_path` via `monkeypatch` para nunca
tocar em `backend/outputs/{images,references}/` real.

Cobre REQ-002 (custom-http-app) da change `consolidate-http-routes-langgraph`:
- `GET /api/images` — listagem paginada (`limit`/`offset`), formato de resposta.
- `GET /api/images/{filename}` — 200 para PNG existente, 400 para path
  traversal e extensão inválida, 404 para arquivo inexistente.
- `POST /api/references` — 200 com upload válido, 400 para
  `ReferenceUploadError` (arquivo vazio/grande demais/formato não suportado).
- `GET /api/references/{filename}` — 200 com mime correto, 400/404 para
  casos inválidos.
"""
from __future__ import annotations

import base64
import io
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.infrastructure.web.images_router as images_router
import src.infrastructure.web.webapp as webapp
from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.users import User

_FAKE_USER = User(
    id="test-user",
    username="tester",
    password_hash="x",
    role="admin",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
)

# 1x1 PNG transparente — passa no `sniff_image_mime` do `reference_store`.
_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


@pytest.fixture
def images_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Cria `IMAGES_DIR` e `REFERENCES_DIR` apontando para um tmp_path.

    Importante: `monkeypatch.setattr` substitui o atributo do MÓDULO
    `images_router`, mas as funções foram capturadas com `IMAGES_DIR` no
    escopo do módulo. Como `IMAGES_DIR` é lido dinamicamente (não congelado
    em closure), apontar o atributo do módulo para o tmp_path é suficiente.
    """
    images_dir = tmp_path / "images"
    references_dir = tmp_path / "references"
    images_dir.mkdir()
    references_dir.mkdir()
    monkeypatch.setattr(images_router, "IMAGES_DIR", images_dir)
    monkeypatch.setattr(images_router, "REFERENCES_DIR", references_dir)
    return images_dir


@pytest.fixture
def client(images_root: Path, monkeypatch: pytest.MonkeyPatch):
    """Cliente FastAPI para o `webapp.app` (sem subir servidor real).

    Faz override de `require_auth` (dependency global aplicada em `webapp.py`,
    task-rest-3) para um usuário fake — estas rotas passaram a exigir sessão
    e este teste cobre apenas o comportamento de `images_router`, não auth.

    `get_file_owner` → None: testes admin seedam o layout legado `IMAGES_DIR`
    (D12 fallback).
    """
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        images_router, "get_file_owner", AsyncMock(return_value=None)
    )
    webapp.app.dependency_overrides[require_auth] = lambda: _FAKE_USER
    try:
        yield TestClient(webapp.app)
    finally:
        webapp.app.dependency_overrides.pop(require_auth, None)


# ---------- GET /api/images ----------


def test_list_images_empty(client: TestClient):
    """Diretório vazio retorna lista vazia, total=0, e ecoa limit/offset."""
    resp = client.get("/api/images")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"images": [], "total": 0, "limit": 20, "offset": 0}


def test_list_images_paginates_and_sorts_newest_first(
    client: TestClient, images_root: Path
):
    """REQ-002: paginação com `limit`/`offset` e ordenação por mtime desc."""
    # Cria 3 PNGs com mtimes espaçados para forçar uma ordem determinística.
    files = []
    for i in range(3):
        path = images_root / f"2026010{i + 1}120000.png"
        path.write_bytes(_PNG_1X1)
        files.append(path)

    # Toca o mtime para o último ser o mais recente.
    import os
    for i, p in enumerate(files):
        os.utime(p, (1_700_000_000 + i, 1_700_000_000 + i))

    # Página 1: limit=2 → primeiros 2 mais recentes
    resp = client.get("/api/images?limit=2&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["images"]) == 2
    # Os 2 primeiros do sort (mtime desc) são os 2 últimos criados.
    returned_names = [item["filename"] for item in body["images"]]
    assert returned_names[0] == "20260103120000.png"
    assert returned_names[1] == "20260102120000.png"
    # Cada item traz filename, url e timestamp
    for item in body["images"]:
        assert item["url"].startswith("/api/images/")
        assert item["url"].endswith(item["filename"])
        assert item["timestamp"]


def test_list_images_offset_skips(client: TestClient, images_root: Path):
    """REQ-002: `offset` pula os primeiros N itens."""
    import os
    paths = []
    for i in range(3):
        p = images_root / f"2026010{i + 1}120000.png"
        p.write_bytes(_PNG_1X1)
        os.utime(p, (1_700_000_000 + i, 1_700_000_000 + i))
        paths.append(p)

    resp = client.get("/api/images?limit=10&offset=1")
    body = resp.json()
    assert body["total"] == 3
    assert body["offset"] == 1
    # Pula o primeiro (mais recente) e devolve os outros 2.
    assert [i["filename"] for i in body["images"]] == [
        "20260102120000.png",
        "20260101120000.png",
    ]


def test_list_images_rejects_invalid_limit(client: TestClient):
    """`limit=0` viola o `ge=1` declarado no router → 422 do FastAPI."""
    resp = client.get("/api/images?limit=0")
    assert resp.status_code == 422


# ---------- GET /api/images/{filename} ----------


def test_serve_image_ok(client: TestClient, images_root: Path):
    """REQ-002: PNG existente → 200 com Content-Type image/png."""
    name = "20260101120000.png"
    (images_root / name).write_bytes(_PNG_1X1)
    resp = client.get(f"/api/images/{name}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content == _PNG_1X1


def test_serve_image_blocks_path_traversal(client: TestClient):
    """REQ-002: filenames com `..` ou `\\` → 400 (bloqueados pelo handler).

    NOTA: o caso isolado de URL `..` (sem path) e qualquer URL contendo
    `/` como separador são bloqueados pelo Starlette no nível de
    roteamento e devolvem 404, porque o framework normaliza o path antes de
    chegar ao handler. Aqui testamos o que o handler REALMENTE bloqueia —
    filenames que carregam `..` como substring (e.g. `..png`,
    `a..b.png`) ou `\\` (que NÃO é separador de URL e portanto chega
    intacto ao handler).
    """
    for bad in ("..png", "a..b.png", "a\\b.png"):
        resp = client.get(f"/api/images/{bad}")
        assert resp.status_code == 400, f"expected 400 for {bad!r}, got {resp.status_code}"


def test_serve_image_blocks_non_png(client: TestClient):
    """REQ-002: extensão diferente de .png → 400."""
    resp = client.get("/api/images/photo.jpg")
    assert resp.status_code == 400
    assert "PNG" in resp.json()["detail"]


def test_serve_image_404_when_missing(client: TestClient, images_root: Path):
    """REQ-002: arquivo inexistente → 404."""
    resp = client.get("/api/images/does_not_exist.png")
    assert resp.status_code == 404


# ---------- POST /api/references ----------


def test_upload_reference_ok(
    client: TestClient,
    images_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """REQ-002 / session-file-sandbox: upload válido em files/<uid>/attachment/."""
    from unittest.mock import AsyncMock

    files_root = tmp_path / "files"
    monkeypatch.setenv("FILES_DIR", str(files_root))
    monkeypatch.setattr(images_router, "record_ownership", AsyncMock())

    resp = client.post(
        "/api/references",
        files={"file": ("any.png", io.BytesIO(_PNG_1X1), "image/png")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) == {"path", "url", "filename"}
    assert body["url"].startswith("/api/references/")
    assert body["url"].endswith(body["filename"])
    saved = Path(body["path"])
    assert saved.exists()
    assert saved.parent == files_root / "test-user" / "attachment"


def test_upload_reference_rejects_empty(client: TestClient):
    """REQ-002: payload vazio → 400 (ReferenceUploadError)."""
    resp = client.post(
        "/api/references",
        files={"file": ("empty.png", io.BytesIO(b""), "image/png")},
    )
    assert resp.status_code == 400
    assert "vazio" in resp.json()["detail"]


def test_upload_reference_rejects_non_image(client: TestClient):
    """REQ-002: bytes que não são imagem → 400."""
    resp = client.post(
        "/api/references",
        files={"file": ("fake.png", io.BytesIO(b"isto nao e uma imagem"), "image/png")},
    )
    assert resp.status_code == 400
    assert "formato suportado" in resp.json()["detail"]


# ---------- GET /api/references/{filename} ----------


def test_serve_reference_ok(client: TestClient, images_root: Path):
    """Reference válida (PNG) → 200 com mime image/png e Cache-Control."""
    name = "20260101120000-aabbccdd.png"
    ref_path = images_root.parent / "references" / name
    ref_path.write_bytes(_PNG_1X1)
    resp = client.get(f"/api/references/{name}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content == _PNG_1X1
    assert resp.headers.get("cache-control")


def test_serve_reference_blocks_traversal(client: TestClient):
    """Filenames com `..` ou `\\` → 400 (bloqueados pelo handler).

    `..` puro e `/` no meio do path são normalizados pelo Starlette
    (404), ver nota em `test_serve_image_blocks_path_traversal`.
    """
    for bad in ("..png", "a..b.png", "a\\b.png"):
        resp = client.get(f"/api/references/{bad}")
        assert resp.status_code == 400, f"expected 400 for {bad!r}"


def test_serve_reference_blocks_unsupported_extension(client: TestClient):
    """Extensão fora de `_REFERENCE_MEDIA_TYPES` → 400."""
    resp = client.get("/api/references/photo.tif")
    assert resp.status_code == 400
    assert "Unsupported" in resp.json()["detail"]


def test_serve_reference_404_when_missing(client: TestClient):
    """Reference inexistente → 404."""
    resp = client.get("/api/references/ghost.png")
    assert resp.status_code == 404


# ---------- Ownership isolation (fix-image-list-user-isolation) ----------


_USER = User(
    id="user-u",
    username="alice",
    password_hash="x",
    role="user",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
)


@pytest.fixture
def user_client(images_root: Path, monkeypatch: pytest.MonkeyPatch):
    """Cliente autenticado como role=user (não admin)."""
    webapp.app.dependency_overrides[require_auth] = lambda: _USER
    try:
        yield TestClient(webapp.app)
    finally:
        webapp.app.dependency_overrides.pop(require_auth, None)


def test_list_images_user_only_sees_owned(
    user_client: TestClient,
    images_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """REQ-003 / D7: role=user lista só filenames owned sob files/<uid>/images/."""
    files_root = tmp_path / "files"
    owned_dir = files_root / "user-u" / "images"
    owned_dir.mkdir(parents=True)
    (owned_dir / "owned.png").write_bytes(_PNG_1X1)
    (files_root / "other" / "images").mkdir(parents=True)
    (files_root / "other" / "images" / "other.png").write_bytes(_PNG_1X1)
    (images_root / "orphan.png").write_bytes(_PNG_1X1)
    monkeypatch.setenv("FILES_DIR", str(files_root))

    async def _owned(*, kind: str, user_id: str):
        assert kind == "image"
        assert user_id == "user-u"
        return frozenset({"owned.png"})

    monkeypatch.setattr(images_router, "list_owned_filenames", _owned)

    resp = user_client.get("/api/images")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert [i["filename"] for i in body["images"]] == ["owned.png"]


def test_serve_image_user_denied_for_foreign(
    user_client: TestClient, images_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """REQ-002: get de imagem alheia → 404 opaco."""
    name = "foreign.png"
    (images_root / name).write_bytes(_PNG_1X1)

    async def _deny(*, kind: str, filename: str, user: User):
        assert kind == "image"
        assert filename == name
        assert user.id == "user-u"
        return False

    monkeypatch.setattr(images_router, "is_authorized", _deny)

    resp = user_client.get(f"/api/images/{name}")
    assert resp.status_code == 404
    assert resp.content != _PNG_1X1


def test_serve_image_user_allowed_for_own(
    user_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    name = "mine.png"
    files_root = tmp_path / "files"
    path = files_root / "user-u" / "images" / name
    path.parent.mkdir(parents=True)
    path.write_bytes(_PNG_1X1)
    monkeypatch.setenv("FILES_DIR", str(files_root))

    async def _allow(*, kind: str, filename: str, user: User):
        return True

    monkeypatch.setattr(images_router, "is_authorized", _allow)
    monkeypatch.setattr(
        images_router, "get_file_owner", AsyncMock(return_value="user-u")
    )

    resp = user_client.get(f"/api/images/{name}")
    assert resp.status_code == 200
    assert resp.content == _PNG_1X1
