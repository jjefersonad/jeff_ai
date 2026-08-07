"""Testes do domínio PdfSpec (add-pdf-creation-tool-task-domain-1)."""
from __future__ import annotations

import pytest

from src.domain.documents import Paragraph, PdfSpec
from src.domain.shared.errors import DomainError


def test_pdf_spec_valid_with_paragraph() -> None:
    """Unit: PdfSpec válido com paragraph."""
    spec = PdfSpec(title="Relatório", blocks=(Paragraph("corpo"),))
    assert spec.kind == "pdf"
    assert spec.extension == ".pdf"
    assert spec.title == "Relatório"
    assert len(spec.blocks) == 1
    assert spec.blocks[0].text == "corpo"


def test_pdf_spec_rejects_empty_blocks() -> None:
    """Unit: PdfSpec rejeita blocks vazios."""
    with pytest.raises(DomainError, match="blocks"):
        PdfSpec(title="Relatório", blocks=())


def test_pdf_spec_rejects_unsupported_block_type() -> None:
    """Acceptance: tipos de bloco inválidos levantam DomainError."""
    with pytest.raises(DomainError, match="não suportado"):
        PdfSpec(title="Relatório", blocks=("não é bloco",))  # type: ignore[arg-type]
