"""list_owned_files — session-file-sandbox attach-2 unit-1 (REQ-003)."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

import src.tools.list_owned_files_tool as mod


class _FakeCursor:
    def __init__(self, *, attachments: list[tuple], generated: list[tuple]) -> None:
        self._attachments = attachments
        self._generated = generated
        self.executed: list[tuple[str, tuple | None]] = []
        self._pending: list[tuple] = []

    async def __aenter__(self) -> "_FakeCursor":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def execute(self, query: str, params: tuple | None = None) -> None:
        self.executed.append((query, params))
        q = " ".join(query.split()).lower()
        if "from chat_attachments" in q:
            self._pending = list(self._attachments)
        elif "from generated_files" in q:
            self._pending = list(self._generated)
        else:
            self._pending = []

    async def fetchall(self) -> list[tuple]:
        return self._pending


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    async def __aenter__(self) -> "_FakeConnection":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self._cursor


class _FakePool:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def connection(self) -> _FakeConnection:
        return _FakeConnection(self._cursor)


def _parse(result: str) -> Any:
    return json.loads(result)


@pytest.mark.asyncio
async def test_list_owned_files_user_sees_only_own(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN role=user A THEN results include A's files and exclude B."""
    monkeypatch.setenv("FILES_DIR", str(tmp_path))
    monkeypatch.setenv("BASE_URL", "http://backend.test")

    attachments = [
        (
            "att-a",
            "user-a",
            "thread-1",
            "logo.png",
            "image/png",
            10,
            str(tmp_path / "user-a" / "attachment" / "att-a.png"),
        ),
    ]
    generated = [
        ("user-a", "docx", "report.docx"),
        ("user-a", "image", "shot.png"),
        ("user-a", "reference", "ref.png"),
    ]
    cursor = _FakeCursor(attachments=attachments, generated=generated)
    monkeypatch.setattr(mod, "get_pool", lambda: _FakePool(cursor))

    with (
        patch.object(mod, "resolve_user_id", new=AsyncMock(return_value="user-a")),
        patch.object(mod, "_resolve_role", return_value="user"),
    ):
        raw = await mod.list_owned_files.ainvoke({})

    data = _parse(raw)
    assert isinstance(data, list)
    filenames = {item["filename"] for item in data}
    assert "logo.png" in filenames
    assert "report.docx" in filenames
    assert "shot.png" in filenames
    assert "ref.png" in filenames

    for item in data:
        assert "storage_path" in item
        assert "url" in item
        assert "user-b" not in item["storage_path"].lower()
        assert "/files/user-b/" not in item["storage_path"]

    # Attachment URL + derived storage under files/<uid>/attachment/
    att = next(i for i in data if i["filename"] == "logo.png")
    assert att["url"].endswith("/api/attachments/att-a")
    assert "/files/user-a/attachment/" in att["storage_path"].replace("\\", "/") or str(
        tmp_path / "user-a" / "attachment"
    ) in att["storage_path"]

    doc = next(i for i in data if i["filename"] == "report.docx")
    assert doc["kind"] == "docx"
    assert "/api/files/docx/report.docx" in doc["url"]
    assert str(tmp_path / "user-a" / "docs" / "report.docx") in doc["storage_path"]

    img = next(i for i in data if i["filename"] == "shot.png")
    assert img["kind"] == "image"
    assert "/api/images/shot.png" in img["url"]


@pytest.mark.asyncio
async def test_list_owned_files_fail_closed_without_user_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN user_id missing THEN fail-closed (like search_memory)."""
    with (
        patch.object(mod, "resolve_user_id", new=AsyncMock(return_value=None)),
        patch.object(mod, "_resolve_role", return_value="user"),
    ):
        raw = await mod.list_owned_files.ainvoke({})

    assert raw.startswith("ERRO:")
    assert "identidade" in raw.lower()
    assert "storage_path" not in raw


@pytest.mark.asyncio
async def test_list_owned_files_admin_may_list_all(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN role=admin THEN MAY include files from multiple users."""
    monkeypatch.setenv("FILES_DIR", str(tmp_path))
    monkeypatch.setenv("BASE_URL", "http://backend.test")

    attachments = [
        (
            "att-a",
            "user-a",
            "t1",
            "a.png",
            "image/png",
            1,
            str(tmp_path / "user-a" / "attachment" / "a.png"),
        ),
        (
            "att-b",
            "user-b",
            "t2",
            "b.png",
            "image/png",
            1,
            str(tmp_path / "user-b" / "attachment" / "b.png"),
        ),
    ]
    generated = [
        ("user-a", "pdf", "a.pdf"),
        ("user-b", "pdf", "b.pdf"),
    ]
    cursor = _FakeCursor(attachments=attachments, generated=generated)
    monkeypatch.setattr(mod, "get_pool", lambda: _FakePool(cursor))

    with (
        patch.object(mod, "resolve_user_id", new=AsyncMock(return_value="user-a")),
        patch.object(mod, "_resolve_role", return_value="admin"),
    ):
        raw = await mod.list_owned_files.ainvoke({})

    data = _parse(raw)
    filenames = {item["filename"] for item in data}
    assert "a.png" in filenames and "b.png" in filenames
    assert "a.pdf" in filenames and "b.pdf" in filenames
