"""HTTP resolve under files/<uid>/… (session-file-sandbox http-1 / http-2)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import src.infrastructure.web.documents_router as documents_router
import src.infrastructure.web.images_router as images_router
import src.infrastructure.web.webapp as webapp
from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.users import User

_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
    b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)

_OWNER = User(
    id="owner-uid",
    username="owner",
    password_hash="x",
    role="user",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
)

_ADMIN = User(
    id="admin-uid",
    username="admin",
    password_hash="x",
    role="admin",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
)


@pytest.fixture
def files_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "files"
    root.mkdir()
    monkeypatch.setenv("FILES_DIR", str(root))
    return root


@pytest.fixture
def owner_client():
    webapp.app.dependency_overrides[require_auth] = lambda: _OWNER
    try:
        yield TestClient(webapp.app)
    finally:
        webapp.app.dependency_overrides.pop(require_auth, None)


@pytest.fixture
def admin_client():
    webapp.app.dependency_overrides[require_auth] = lambda: _ADMIN
    try:
        yield TestClient(webapp.app)
    finally:
        webapp.app.dependency_overrides.pop(require_auth, None)


# --- http-1 unit-1: GET /api/files resolves files/<uid>/docs/ ---------------


def test_get_docx_serves_bytes_from_user_files_docs(
    files_root: Path,
    owner_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """WHEN owner GETs /api/files/docx/<filename> under files/<uid>/docs/

    THEN 200 and public URL shape stays /api/files/docx/<filename>.
    """
    name = "report.docx"
    path = files_root / "owner-uid" / "docs" / name
    path.parent.mkdir(parents=True)
    path.write_bytes(b"PK-docx-from-files")

    monkeypatch.setattr(
        documents_router, "is_authorized", AsyncMock(return_value=True)
    )
    # Owner lookup used to derive files/<uid>/docs/<name> (D13).
    monkeypatch.setattr(
        documents_router,
        "get_file_owner",
        AsyncMock(return_value="owner-uid"),
        raising=False,
    )

    url = f"/api/files/docx/{name}"
    resp = owner_client.get(url)

    assert resp.status_code == 200
    assert resp.content == b"PK-docx-from-files"
    assert url == f"/api/files/docx/{name}"
    assert resp.headers["content-disposition"] == f'attachment; filename="{name}"'


# --- http-1 unit-2: list_images owned + D12 legacy admin-only --------------


def test_list_images_user_only_sees_owned_under_files(
    files_root: Path,
    owner_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """WHEN role=user calls list_images THEN only that user's filenames appear."""
    owned = files_root / "owner-uid" / "images" / "mine.png"
    owned.parent.mkdir(parents=True)
    owned.write_bytes(_PNG_1X1)
    other = files_root / "other-uid" / "images" / "theirs.png"
    other.parent.mkdir(parents=True)
    other.write_bytes(_PNG_1X1)

    # Global legacy dir still has an orphan — must not leak into user list.
    legacy = tmp_path / "outputs" / "images"
    legacy.mkdir(parents=True)
    (legacy / "orphan.png").write_bytes(_PNG_1X1)
    monkeypatch.setattr(images_router, "IMAGES_DIR", legacy)

    async def _owned(*, kind: str, user_id: str):
        assert kind == "image"
        assert user_id == "owner-uid"
        return frozenset({"mine.png"})

    monkeypatch.setattr(images_router, "list_owned_filenames", _owned)

    resp = owner_client.get("/api/images")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert [i["filename"] for i in body["images"]] == ["mine.png"]
    assert body["images"][0]["url"] == "/api/images/mine.png"


def test_user_get_legacy_outputs_image_orphan_is_404(
    owner_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """WHEN role=user GETs a legacy outputs/images orphan THEN 404."""
    legacy = tmp_path / "outputs" / "images"
    legacy.mkdir(parents=True)
    name = "orphan.png"
    (legacy / name).write_bytes(_PNG_1X1)
    monkeypatch.setattr(images_router, "IMAGES_DIR", legacy)
    monkeypatch.setattr(
        images_router, "is_authorized", AsyncMock(return_value=False)
    )

    resp = owner_client.get(f"/api/images/{name}")
    assert resp.status_code == 404
    assert resp.content != _PNG_1X1


def test_admin_get_legacy_outputs_image_orphan_is_200(
    admin_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """WHEN admin GETs the same legacy file that exists on disk THEN 200 (D12)."""
    legacy = tmp_path / "outputs" / "images"
    legacy.mkdir(parents=True)
    name = "orphan.png"
    (legacy / name).write_bytes(_PNG_1X1)
    monkeypatch.setattr(images_router, "IMAGES_DIR", legacy)
    monkeypatch.setattr(
        images_router, "is_authorized", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        images_router, "get_file_owner", AsyncMock(return_value=None), raising=False
    )

    resp = admin_client.get(f"/api/images/{name}")
    assert resp.status_code == 200
    assert resp.content == _PNG_1X1


def test_get_image_serves_bytes_from_user_files_images(
    files_root: Path,
    owner_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """GET /api/images/<filename> resolves files/<owner>/images/ (REQ-007)."""
    name = "20260101120000.png"
    path = files_root / "owner-uid" / "images" / name
    path.parent.mkdir(parents=True)
    path.write_bytes(_PNG_1X1)

    monkeypatch.setattr(
        images_router, "is_authorized", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        images_router,
        "get_file_owner",
        AsyncMock(return_value="owner-uid"),
        raising=False,
    )

    resp = owner_client.get(f"/api/images/{name}")
    assert resp.status_code == 200
    assert resp.content == _PNG_1X1


# --- http-2 unit-1: GET /api/attachments/{id} ownership --------------------


def test_owner_gets_own_attachment_bytes(
    files_root: Path,
    owner_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """WHEN owner GETs /api/attachments/{id} THEN 200 with stored bytes/content-type."""
    import src.infrastructure.web.attachments_router as attachments_router

    att_id = "att-owner-1"
    path = files_root / "owner-uid" / "attachment" / f"{att_id}.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(_PNG_1X1)

    class _Row:
        attachment_id = att_id
        user_id = "owner-uid"
        thread_id = "t1"
        filename = "logo.png"
        content_type = "image/png"
        size_bytes = len(_PNG_1X1)
        storage_path = str(path)

    async def _get(*, attachment_id: str):
        assert attachment_id == att_id
        return _Row()

    monkeypatch.setattr(
        attachments_router, "get_attachment", _get, raising=False
    )

    resp = owner_client.get(f"/api/attachments/{att_id}")
    assert resp.status_code == 200
    assert resp.content == _PNG_1X1
    assert resp.headers["content-type"].startswith("image/png")


def test_other_user_gets_404_for_foreign_attachment(
    files_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """WHEN another role=user GETs the same id THEN 404."""
    import src.infrastructure.web.attachments_router as attachments_router

    other = User(
        id="other-uid",
        username="other",
        password_hash="x",
        role="user",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    att_id = "att-owner-1"
    path = files_root / "owner-uid" / "attachment" / f"{att_id}.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(_PNG_1X1)

    class _Row:
        attachment_id = att_id
        user_id = "owner-uid"
        thread_id = "t1"
        filename = "logo.png"
        content_type = "image/png"
        size_bytes = len(_PNG_1X1)
        storage_path = str(path)

    async def _get(*, attachment_id: str):
        return _Row()

    monkeypatch.setattr(
        attachments_router, "get_attachment", _get, raising=False
    )

    webapp.app.dependency_overrides[require_auth] = lambda: other
    try:
        client = TestClient(webapp.app)
        resp = client.get(f"/api/attachments/{att_id}")
    finally:
        webapp.app.dependency_overrides.pop(require_auth, None)

    assert resp.status_code == 404
    assert resp.content != _PNG_1X1


# --- http-2 unit-2: references auth + ownership ---------------------------


def test_unauthenticated_references_post_and_get_return_401(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """WHEN unauthenticated POST/GET /api/references is attempted THEN 401."""
    import io

    # No require_auth override — global dependency must reject.
    webapp.app.dependency_overrides.pop(require_auth, None)
    monkeypatch.setattr(
        images_router, "REFERENCES_DIR", tmp_path / "references"
    )
    (tmp_path / "references").mkdir(parents=True, exist_ok=True)

    client = TestClient(webapp.app)
    post = client.post(
        "/api/references",
        files={"file": ("any.png", io.BytesIO(_PNG_1X1), "image/png")},
    )
    get = client.get("/api/references/ghost.png")
    assert post.status_code == 401
    assert get.status_code == 401


def test_user_cannot_get_another_users_reference(
    files_root: Path,
    owner_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """WHEN role=user GETs another user's reference filename THEN 404.

    Bytes also exist under legacy REFERENCES_DIR so a missing ownership gate
    would incorrectly return 200 — the handler MUST call is_authorized.
    """
    name = "20260101120000-aabbccdd.png"
    owned_path = files_root / "other-uid" / "attachment" / name
    owned_path.parent.mkdir(parents=True)
    owned_path.write_bytes(_PNG_1X1)

    legacy = tmp_path / "references"
    legacy.mkdir(parents=True)
    (legacy / name).write_bytes(_PNG_1X1)
    monkeypatch.setattr(images_router, "REFERENCES_DIR", legacy)

    monkeypatch.setattr(
        images_router, "is_authorized", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        images_router,
        "get_file_owner",
        AsyncMock(return_value="other-uid"),
        raising=False,
    )

    resp = owner_client.get(f"/api/references/{name}")
    assert resp.status_code == 404
    assert resp.content != _PNG_1X1


def test_owner_gets_reference_from_user_files_attachment(
    files_root: Path,
    owner_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """Owner GET resolves files/<uid>/attachment/ (kind=reference → attachment/)."""
    name = "20260101120000-mine.png"
    path = files_root / "owner-uid" / "attachment" / name
    path.parent.mkdir(parents=True)
    path.write_bytes(_PNG_1X1)

    monkeypatch.setattr(
        images_router, "is_authorized", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        images_router,
        "get_file_owner",
        AsyncMock(return_value="owner-uid"),
        raising=False,
    )

    resp = owner_client.get(f"/api/references/{name}")
    assert resp.status_code == 200
    assert resp.content == _PNG_1X1
