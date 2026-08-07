"""Adapter de criação de documentos PDF via fpdf2 (implementa o port)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from fpdf import FPDF

from src.application.ports.document_writer import DocumentWriterPort
from src.domain.documents import (
    DocumentResult,
    DocumentSpec,
    Heading,
    ImageRef,
    ListBlock,
    Paragraph,
    PdfSpec,
    Table,
)
from src.domain.shared.errors import DomainError
from src.infrastructure.documents.output_target import DocumentOutput
from src.infrastructure.documents.pdf_fonts import (
    DEJAVU_SANS_BOLD_PATH,
    DEJAVU_SANS_PATH,
)

_FONT_FAMILY = "DejaVu"


class PdfWriter(DocumentWriterPort):
    """Gera um `.pdf` a partir de um `PdfSpec` usando apenas fpdf2.

    Usa fontes TTF empacotadas em `backend/assets/fonts/` (DejaVu) para
    suporte a PT-BR. O documento é montado em memória e só é escrito no
    final — falhas durante a montagem (fonte ausente, imagem faltando)
    não deixam arquivo parcial.
    """

    def __init__(
        self,
        *,
        output_dir: Path | None = None,
        url_prefix: str = "/api/files",
    ) -> None:
        """Configura o destino e o prefixo de URL do writer."""
        self._output = DocumentOutput("pdf", output_dir=output_dir, url_prefix=url_prefix)

    async def write(self, spec: DocumentSpec) -> DocumentResult:
        """Gera o `.pdf` do `spec` (fora do event loop) e retorna o resultado."""
        if not isinstance(spec, PdfSpec):
            raise TypeError("PdfWriter só aceita PdfSpec.")
        return await asyncio.to_thread(self._write_sync, spec)

    def _write_sync(self, spec: PdfSpec) -> DocumentResult:
        pdf = self._build_pdf(spec)
        path, url = self._output.allocate(spec.extension)
        # fpdf2 escreve bytes; falhas anteriores já teriam levantado.
        pdf.output(str(path))
        return DocumentResult(path=str(path), url=url, metadata=spec.metadata())

    def _build_pdf(self, spec: PdfSpec) -> FPDF:
        self._ensure_fonts()
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_font(_FONT_FAMILY, fname=str(DEJAVU_SANS_PATH))
        pdf.add_font(_FONT_FAMILY, style="B", fname=str(DEJAVU_SANS_BOLD_PATH))
        pdf.add_page()
        pdf.set_font(_FONT_FAMILY, style="B", size=16)
        pdf.multi_cell(0, 10, spec.title)
        pdf.ln(4)

        for block in spec.blocks:
            self._render_block(pdf, block)
        return pdf

    @staticmethod
    def _ensure_fonts() -> None:
        if not DEJAVU_SANS_PATH.is_file() or not DEJAVU_SANS_BOLD_PATH.is_file():
            raise DomainError(
                f"Fonte DejaVu ausente: esperado {DEJAVU_SANS_PATH} e "
                f"{DEJAVU_SANS_BOLD_PATH}."
            )

    def _render_block(self, pdf: FPDF, block: object) -> None:
        pdf.set_x(pdf.l_margin)
        if isinstance(block, Heading):
            size = max(18 - (block.level - 1) * 2, 11)
            pdf.set_font(_FONT_FAMILY, style="B", size=size)
            pdf.multi_cell(0, 8, block.text)
            pdf.ln(2)
        elif isinstance(block, Paragraph):
            pdf.set_font(_FONT_FAMILY, size=11)
            pdf.multi_cell(0, 6, block.text)
            pdf.ln(2)
        elif isinstance(block, ListBlock):
            self._render_list(pdf, block)
        elif isinstance(block, Table):
            self._render_table(pdf, block)
        elif isinstance(block, ImageRef):
            self._render_image(pdf, block)

    @staticmethod
    def _render_list(pdf: FPDF, block: ListBlock) -> None:
        pdf.set_font(_FONT_FAMILY, size=11)
        for index, item in enumerate(block.items, start=1):
            prefix = f"{index}. " if block.ordered else "- "
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 6, f"{prefix}{item}")
        pdf.ln(2)

    @staticmethod
    def _render_table(pdf: FPDF, block: Table) -> None:
        with pdf.table() as table:
            for row_idx, row in enumerate(block.rows):
                if block.header and row_idx == 0:
                    pdf.set_font(_FONT_FAMILY, style="B", size=10)
                else:
                    pdf.set_font(_FONT_FAMILY, size=10)
                cells = table.row()
                for value in row:
                    cells.cell(value)
        pdf.ln(4)

    @staticmethod
    def _render_image(pdf: FPDF, block: ImageRef) -> None:
        path = Path(block.path)
        if not path.is_file():
            raise RuntimeError(f"Imagem não encontrada: {block.path!r}.")
        width = (block.width_inches or 3.0) * 25.4  # inches → mm
        pdf.image(str(path), w=width)
        pdf.ln(4)
