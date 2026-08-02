"""Testes de `scripts/backfill_generated_files_ownership.py`.

resource-ownership-model REQ-003: arquivos pré-existentes (sem dono) ganham
uma linha em `generated_files` atribuída ao admin de bootstrap. Espelha o
estilo de `test_wait_for_postgres.py` (import direto do script, fora de
pacote) e `test_auth_schema.py` (fake connection/cursor síncronos).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import backfill_generated_files_ownership as backfill  # noqa: E402


class _FakeCursor:
    def __init__(self, executed: list[tuple[str, tuple | None]], fetchone_queue: list[tuple | None]) -> None:
        self._executed = executed
        self._fetchone_queue = fetchone_queue

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def execute(self, query: str, params: tuple | None = None) -> None:
        self._executed.append((query, params))

    def fetchone(self) -> tuple | None:
        if self._fetchone_queue:
            return self._fetchone_queue.pop(0)
        return None


class _FakeConnection:
    def __init__(self, fetchone_queue: list[tuple | None]) -> None:
        self.executed: list[tuple[str, tuple | None]] = []
        self._fetchone_queue = list(fetchone_queue)

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self.executed, self._fetchone_queue)


def _make_tree(tmp_path: Path) -> tuple[Path, Path]:
    documents_dir = tmp_path / "documents"
    images_dir = tmp_path / "images"
    (documents_dir / "docx").mkdir(parents=True)
    (documents_dir / "xlsx").mkdir(parents=True)
    (documents_dir / "pptx").mkdir(parents=True)
    images_dir.mkdir(parents=True)
    return documents_dir, images_dir


# --- find_existing_files ------------------------------------------------


def test_find_existing_files_lists_documents_and_images(tmp_path: Path) -> None:
    documents_dir, images_dir = _make_tree(tmp_path)
    (documents_dir / "docx" / "report.docx").write_text("x")
    (documents_dir / "xlsx" / "sheet.xlsx").write_text("x")
    (documents_dir / "pptx" / "deck.pptx").write_text("x")
    (images_dir / "20260706223050.png").write_bytes(b"x")

    entries = backfill.find_existing_files(documents_dir, images_dir)

    assert entries == [
        ("docx", "report.docx"),
        ("xlsx", "sheet.xlsx"),
        ("pptx", "deck.pptx"),
        ("image", "20260706223050.png"),
    ]


def test_find_existing_files_ignores_non_png_in_images_dir(tmp_path: Path) -> None:
    documents_dir, images_dir = _make_tree(tmp_path)
    (images_dir / "20260706223050.png").write_bytes(b"x")
    (images_dir / "20260706223050_metadata.json").write_text("{}")

    entries = backfill.find_existing_files(documents_dir, images_dir)

    assert entries == [("image", "20260706223050.png")]


def test_find_existing_files_tolerates_missing_directories(tmp_path: Path) -> None:
    entries = backfill.find_existing_files(tmp_path / "no-documents", tmp_path / "no-images")

    assert entries == []


# --- resolve_admin_id ----------------------------------------------------


def test_resolve_admin_id_returns_first_admin() -> None:
    conn = _FakeConnection(fetchone_queue=[("admin-id-1",)])

    result = backfill.resolve_admin_id(conn)

    assert result == "admin-id-1"
    query, _ = conn.executed[0]
    assert "role = 'admin'" in query


def test_resolve_admin_id_raises_when_no_admin_exists() -> None:
    conn = _FakeConnection(fetchone_queue=[None])

    with pytest.raises(backfill.BackfillError):
        backfill.resolve_admin_id(conn)


# --- run_backfill ---------------------------------------------------------


def test_run_backfill_dry_run_does_not_insert(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    documents_dir, images_dir = _make_tree(tmp_path)
    (documents_dir / "docx" / "report.docx").write_text("x")

    conn = _FakeConnection(fetchone_queue=[("admin-id-1",)])
    monkeypatch.setattr(backfill.psycopg, "connect", lambda *a, **kw: conn)

    rows = backfill.run_backfill(
        "postgresql://fake", documents_dir=documents_dir, images_dir=images_dir, dry_run=True
    )

    assert rows == [("docx", "report.docx", "admin-id-1")]
    inserts = [q for q, _ in conn.executed if q.strip().startswith("INSERT")]
    assert inserts == []


def test_run_backfill_inserts_rows_owned_by_admin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    documents_dir, images_dir = _make_tree(tmp_path)
    (documents_dir / "docx" / "report.docx").write_text("x")
    (images_dir / "pic.png").write_bytes(b"x")

    conn = _FakeConnection(
        fetchone_queue=[("admin-id-1",), ("row-1",), ("row-2",)]
    )
    monkeypatch.setattr(backfill.psycopg, "connect", lambda *a, **kw: conn)

    rows = backfill.run_backfill(
        "postgresql://fake", documents_dir=documents_dir, images_dir=images_dir, dry_run=False
    )

    assert rows == [("docx", "report.docx", "admin-id-1"), ("image", "pic.png", "admin-id-1")]
    inserts = [(q, p) for q, p in conn.executed if q.strip().startswith("INSERT")]
    assert len(inserts) == 2
    query, params = inserts[0]
    assert "INSERT INTO generated_files" in query
    assert "ON CONFLICT (kind, filename) DO NOTHING" in query
    assert params == ("admin-id-1", "docx", "report.docx")


def test_run_backfill_is_idempotent_on_conflict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Segunda execução: `ON CONFLICT DO NOTHING` não retorna linha (sem RETURNING),
    então o arquivo já existente não é recontado como inserido."""
    documents_dir, images_dir = _make_tree(tmp_path)
    (documents_dir / "docx" / "report.docx").write_text("x")

    conn = _FakeConnection(fetchone_queue=[("admin-id-1",), None])
    monkeypatch.setattr(backfill.psycopg, "connect", lambda *a, **kw: conn)

    rows = backfill.run_backfill(
        "postgresql://fake", documents_dir=documents_dir, images_dir=images_dir, dry_run=False
    )

    assert rows == []
