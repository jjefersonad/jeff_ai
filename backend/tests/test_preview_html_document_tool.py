"""Testes da tool `preview_html_document` (html-document-tools-task-preview-1)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import src.tools.preview_html_document_tool as preview_tool
from src.models.html_document_input import HtmlDocumentInput


@pytest.fixture
def documents_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "documents"
    monkeypatch.setattr(preview_tool, "_documents_base_dir", lambda: root)
    return root


async def test_preview_proposal_template_writes_html_and_records_ownership(
    documents_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-1: template proposal → arquivo html + ownership + url."""
    record = AsyncMock()
    monkeypatch.setattr(preview_tool, "record_ownership", record)
    monkeypatch.setattr(
        preview_tool,
        "_document_url_prefix",
        lambda: "http://localhost:3000/api/files",
    )

    out = await preview_tool.preview_html_document.coroutine(
        HtmlDocumentInput(
            template="proposal",
            data={
                "client_name": "Acme",
                "project_title": "Portal",
                "summary": "MVP",
                "investment": "R$ 1",
            },
            title="Proposta Acme",
        )
    )

    assert "error" not in out
    assert out["metadata"]["kind"] == "html"
    assert "/api/files/html/" in out["url"]
    path = Path(out["path"])
    assert path.is_file()
    assert path.parent == documents_root / "html"
    assert path.suffix == ".html"
    body = path.read_text(encoding="utf-8")
    assert "Acme" in body
    assert "<style" in body.lower()  # CSS self-contained
    record.assert_awaited_once_with(kind="html", filename=path.name)


async def test_preview_rejects_invalid_payload_without_file(
    documents_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-2a: entrada inválida → error, sem arquivo."""
    record = AsyncMock()
    monkeypatch.setattr(preview_tool, "record_ownership", record)

    out = await preview_tool.preview_html_document.coroutine("só texto")

    assert "error" in out
    assert "path" not in out
    assert "url" not in out
    record.assert_not_called()
    html_dir = documents_root / "html"
    assert not html_dir.exists() or list(html_dir.glob("*.html")) == []


async def test_preview_ownership_failure_is_fail_closed(
    documents_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-2b: falha de stamp → error, sem sucesso com url."""
    monkeypatch.setattr(
        preview_tool,
        "record_ownership",
        AsyncMock(side_effect=RuntimeError("db down")),
    )
    monkeypatch.setattr(
        preview_tool,
        "_document_url_prefix",
        lambda: "http://localhost:3000/api/files",
    )

    out = await preview_tool.preview_html_document.coroutine(
        HtmlDocumentInput(
            template="proposal",
            data={"client_name": "X", "project_title": "Y"},
        )
    )

    assert "error" in out
    assert "ownership" in out["error"].lower() or "db down" in out["error"].lower()
    assert "path" not in out
    assert "url" not in out


async def test_two_previews_create_distinct_files(
    documents_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-3: dois previews → filenames distintos."""
    record = AsyncMock()
    monkeypatch.setattr(preview_tool, "record_ownership", record)
    monkeypatch.setattr(
        preview_tool,
        "_document_url_prefix",
        lambda: "/api/files",
    )

    payload = HtmlDocumentInput(
        html="<p>v1</p>",
        css="p { color: red; }",
        title="A",
    )
    first = await preview_tool.preview_html_document.coroutine(payload)
    second = await preview_tool.preview_html_document.coroutine(
        HtmlDocumentInput(html="<p>v2</p>", title="B")
    )

    assert first["path"] != second["path"]
    names = {Path(first["path"]).name, Path(second["path"]).name}
    assert len(names) == 2
    for name in names:
        assert (documents_root / "html" / name).is_file()
    assert record.await_count == 2


async def test_preview_rejects_html_and_template_together(
    documents_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Payload com html+template (via JSON) → error sem arquivo."""
    monkeypatch.setattr(preview_tool, "record_ownership", AsyncMock())
    raw = json.dumps(
        {
            "html": "<p>x</p>",
            "template": "proposal",
            "data": {},
        }
    )
    out = await preview_tool.preview_html_document.coroutine(raw)
    assert "error" in out
    assert "path" not in out
    html_dir = documents_root / "html"
    assert not html_dir.exists() or list(html_dir.glob("*.html")) == []
