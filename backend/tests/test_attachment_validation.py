"""Testes de `attachment_validation` (chat-file-attachment REQ-001/REQ-003).

Lógica pura de sniff por magic bytes + limite de tamanho — sem FastAPI, sem
rede, sem persistência. Espelha o estilo de `test_reference_store.py`.
"""
from __future__ import annotations

import io
import zipfile

import pytest

from src.infrastructure.media.attachment_validation import (
    AttachmentValidationError,
    enforce_size_limit,
    sniff_and_validate,
)

_PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< >>\nendobj\n%%EOF"


def _ooxml_bytes(marker_entry: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(marker_entry, "<root/>")
    return buffer.getvalue()


def test_sniff_and_validate_accepts_genuine_pdf():
    """REQ-001: bytes com assinatura PDF real são aceitos como application/pdf."""
    content_type = sniff_and_validate(_PDF_BYTES, declared_filename="report.pdf")
    assert content_type == "application/pdf"


def test_sniff_and_validate_accepts_genuine_docx():
    data = _ooxml_bytes("word/document.xml")
    content_type = sniff_and_validate(data, declared_filename="report.docx")
    assert content_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


def test_sniff_and_validate_accepts_genuine_xlsx():
    data = _ooxml_bytes("xl/workbook.xml")
    content_type = sniff_and_validate(data, declared_filename="sheet.xlsx")
    assert content_type == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def test_sniff_and_validate_accepts_text_csv_by_extension():
    content_type = sniff_and_validate(b"a,b,c\n1,2,3\n", declared_filename="data.csv")
    assert content_type == "text/csv"


def test_sniff_and_validate_accepts_text_txt_by_extension():
    content_type = sniff_and_validate(b"hello world\n", declared_filename="notes.txt")
    assert content_type == "text/plain"


def test_sniff_and_validate_rejects_content_mismatching_declared_type():
    """REQ-003: bytes que não correspondem a nenhum formato suportado (ex.: um
    executável renomeado para "report.pdf") são recusados, mesmo com nome/MIME
    declarados de um formato suportado."""
    fake_executable = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 32
    with pytest.raises(AttachmentValidationError, match="formato suportado"):
        sniff_and_validate(fake_executable, declared_filename="report.pdf")


def test_sniff_and_validate_rejects_empty():
    with pytest.raises(AttachmentValidationError, match="vazio"):
        sniff_and_validate(b"", declared_filename="report.pdf")


def test_sniff_and_validate_rejects_corrupted_ooxml_zip():
    """Zip válido mas sem as entradas internas de docx/xlsx é recusado."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("something.txt", "not office")
    with pytest.raises(AttachmentValidationError):
        sniff_and_validate(buffer.getvalue(), declared_filename="report.docx")


def test_enforce_size_limit_rejects_oversized_file():
    """REQ-003: arquivo acima do limite configurado é recusado antes de persistir."""
    with pytest.raises(AttachmentValidationError, match="tamanho máximo"):
        enforce_size_limit(size_bytes=11, max_bytes=10)


def test_enforce_size_limit_accepts_file_within_limit():
    enforce_size_limit(size_bytes=10, max_bytes=10)
