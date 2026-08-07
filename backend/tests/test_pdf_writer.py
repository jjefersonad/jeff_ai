"""Testes do PdfWriter (add-pdf-creation-tool-task-writer-1)."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from src.domain.documents import (
    Heading,
    ImageRef,
    ListBlock,
    Paragraph,
    PdfSpec,
    Table,
)
from src.domain.shared.errors import DomainError
from src.infrastructure.documents.pdf_writer import PdfWriter


def _make_png(path: Path, width: int = 2, height: int = 2) -> str:
    def _chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x00\x00\x00\x00" * width for _ in range(height))
    idat = zlib.compress(raw)
    path.write_bytes(sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b""))
    return str(path)


@pytest.fixture
def writer(tmp_path: Path) -> PdfWriter:
    return PdfWriter(output_dir=tmp_path, url_prefix="/api/files")


async def test_writer_creates_valid_pdf_with_blocks(writer: PdfWriter, tmp_path: Path) -> None:
    """Unit: PdfWriter gera PDF com heading+paragraph+list+table."""
    spec = PdfSpec(
        title="Relatório",
        blocks=(
            Heading(text="Seção 1", level=1),
            Paragraph(text="Parágrafo introdutório."),
            ListBlock(items=("Item A", "Item B"), ordered=False),
            Table(rows=(("Col 1", "Col 2"), ("v1", "v2")), header=True),
        ),
    )

    result = await writer.write(spec)

    assert result.url.startswith("/api/files/pdf/")
    assert result.url.endswith(".pdf")
    assert result.metadata["kind"] == "pdf"
    path = Path(result.path)
    assert path.is_file()
    assert path.parent == tmp_path
    assert path.read_bytes()[:4] == b"%PDF"


async def test_writer_accepts_portuguese_accents(writer: PdfWriter) -> None:
    """Unit: PdfWriter aceita acentos PT-BR."""
    spec = PdfSpec(
        title="Situação",
        blocks=(Paragraph(text="Situação financeira do trimestre."),),
    )

    result = await writer.write(spec)

    path = Path(result.path)
    assert path.is_file()
    assert path.stat().st_size > 0
    assert path.read_bytes()[:4] == b"%PDF"


async def test_writer_fails_explicitly_when_font_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acceptance: fonte ausente falha de forma explícita."""
    import src.infrastructure.documents.pdf_writer as pdf_writer_mod

    missing = tmp_path / "missing.ttf"
    monkeypatch.setattr(pdf_writer_mod, "DEJAVU_SANS_PATH", missing)
    monkeypatch.setattr(pdf_writer_mod, "DEJAVU_SANS_BOLD_PATH", missing)

    writer = PdfWriter(output_dir=tmp_path, url_prefix="/api/files")
    spec = PdfSpec(title="X", blocks=(Paragraph("y"),))

    with pytest.raises(DomainError, match="fonte|font|DejaVu"):
        await writer.write(spec)
    assert list(tmp_path.glob("*.pdf")) == []


async def test_writer_embeds_image(writer: PdfWriter, tmp_path: Path) -> None:
    """Acceptance: bloco image embute PNG existente."""
    image_path = tmp_path / "logo.png"
    _make_png(image_path)

    spec = PdfSpec(
        title="Com imagem",
        blocks=(ImageRef(path=str(image_path), width_inches=1.0),),
    )

    result = await writer.write(spec)
    assert Path(result.path).read_bytes()[:4] == b"%PDF"
