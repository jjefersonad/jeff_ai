"""Docstring contract for create_docx_document (fix-docx-table-markdown)."""
from __future__ import annotations

import src.tools.create_docx_document_tool as docx_tool


def test_create_docx_document_docstring_discourages_markdown_tables() -> None:
    doc = docx_tool.create_docx_document.__doc__ or ""
    # LangChain @tool may expose docstring on .coroutine as well.
    if "type=\"table\"" not in doc and "type='table'" not in doc:
        doc = getattr(docx_tool.create_docx_document, "coroutine", docx_tool.create_docx_document).__doc__ or ""

    assert 'type="table"' in doc or "type='table'" in doc
    assert "rows" in doc
    lower = doc.lower()
    assert "markdown" in lower
    assert "paragraph" in lower
