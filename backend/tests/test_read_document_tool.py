"""Testes da tool `read_document` (skill `read-document`).

Esta tool substitui a change `document-reading-tools` abandonada. Faz
pouco, mas o que faz tem que ser correto — entrada inválida, paths
perigosos, formatos não suportados, arquivos grandes, etc.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from src.tools.read_document_tool import (
    _OUTPUT_MAX_CHARS,
    _SUPPORTED_EXTS,
    _detect_format,
    _resolve,
    _truncate,
    read_document,
)
from src.tools.self_extension import REPO_ROOT


# Diretório de scratch dentro do repo para arquivos temporários dos
# testes. Existe (`backend/tests/_tmp_read_doc/`) e é limpo no final.
_SCRATCH_DIR = REPO_ROOT / "backend" / "tests" / "_tmp_read_doc"


@pytest.fixture
def scratch_dir():
    _SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    yield _SCRATCH_DIR
    # Limpa todos os arquivos criados pelos testes desta sessão.
    for p in _SCRATCH_DIR.iterdir():
        if p.is_file():
            p.unlink()
    if _SCRATCH_DIR.exists():
        try:
            _SCRATCH_DIR.rmdir()
        except OSError:
            pass  # tem mais arquivos de outros testes rodando em paralelo


# --------------------------------------------------------------------------- #
# _resolve — guards de path
# --------------------------------------------------------------------------- #
class TestResolve:
    def test_empty_path(self):
        assert isinstance(_resolve(""), str)
        assert "vazio" in _resolve("").lower()

    def test_whitespace_path(self):
        assert isinstance(_resolve("   "), str)

    def test_path_outside_repo_is_rejected(self):
        # Tenta escapar com `..`
        result = _resolve("../../../etc/passwd")
        assert isinstance(result, str)
        assert "negado" in result.lower() or "fora" in result.lower()

    def test_absolute_path_inside_repo_works(self, scratch_dir):
        target = scratch_dir / "test1.txt"
        target.write_text("hello", encoding="utf-8")
        result = _resolve(str(target))
        assert isinstance(result, Path)
        assert result == target

    def test_relative_path_inside_repo_works(self, scratch_dir):
        target = scratch_dir / "test2.txt"
        target.write_text("hello", encoding="utf-8")
        result = _resolve("backend/tests/_tmp_read_doc/test2.txt")
        assert isinstance(result, Path)
        assert result == target

    def test_nonexistent_file(self):
        result = _resolve("tests/_definitely_not_here_xyzzy.txt")
        assert isinstance(result, str)
        assert "não encontrado" in result.lower()

    def test_directory_not_file(self, scratch_dir):
        # Aponta para um diretório que existe dentro do repo
        # (`backend/tests/` existe, mesmo que não tenha permissão de listar).
        result = _resolve("backend/tests")
        assert isinstance(result, str)
        # A mensagem pode ser "não encontrado" (path não existe como
        # arquivo) ou "não é um arquivo" (path existe mas é diretório).
        # Ambas as mensagens rejeitam corretamente a leitura.
        assert any(
            phrase in result.lower()
            for phrase in ("não é um arquivo", "não encontrado", "acesso negado")
        )


# --------------------------------------------------------------------------- #
# _detect_format
# --------------------------------------------------------------------------- #
class TestDetectFormat:
    def test_lowercase_extension(self):
        assert _detect_format(Path("foo.docx")) == "docx"

    def test_uppercase_extension_normalized(self):
        assert _detect_format(Path("foo.PDF")) == "pdf"

    def test_no_extension(self):
        assert _detect_format(Path("foo")) == ""

    def test_multi_dot_filename(self):
        # `foo.tar.gz` → extensão é `gz`
        assert _detect_format(Path("foo.tar.gz")) == "gz"


# --------------------------------------------------------------------------- #
# _truncate
# --------------------------------------------------------------------------- #
class TestTruncate:
    def test_short_text_unchanged(self):
        assert _truncate("hello") == "hello"

    def test_long_text_truncated(self):
        big = "x" * (_OUTPUT_MAX_CHARS + 1000)
        out = _truncate(big)
        assert len(out) < len(big)
        assert "truncado" in out


# --------------------------------------------------------------------------- #
# read_document — happy path
# --------------------------------------------------------------------------- #
class TestReadDocument:
    def test_text_file_returns_content(self, scratch_dir):
        target = scratch_dir / "test.txt"
        target.write_text("olá mundo", encoding="utf-8")
        result = read_document.invoke({"path": "backend/tests/_tmp_read_doc/test.txt"})
        assert "olá mundo" in result
        assert "read_document" in result  # header marker

    def test_markdown_file_returns_content(self, scratch_dir):
        target = scratch_dir / "test.md"
        target.write_text("# Title\n\nSome **bold** text.", encoding="utf-8")
        result = read_document.invoke({"path": "backend/tests/_tmp_read_doc/test.md"})
        assert "Title" in result
        assert "bold" in result

    def test_csv_file_returns_content(self, scratch_dir):
        # markitdown converte CSV em markdown table
        target = scratch_dir / "test.csv"
        target.write_text("name,age\nAlice,30\nBob,25", encoding="utf-8")
        result = read_document.invoke({"path": "backend/tests/_tmp_read_doc/test.csv"})
        assert "Alice" in result
        assert "Bob" in result

    def test_format_hint_overrides_extension(self, scratch_dir):
        # Arquivo sem extensão mas com format_hint="txt"
        target = scratch_dir / "test_noext"
        target.write_text("force this format", encoding="utf-8")
        result = read_document.invoke(
            {
                "path": "backend/tests/_tmp_read_doc/test_noext",
                "format_hint": "txt",
            }
        )
        assert "force this format" in result


# --------------------------------------------------------------------------- #
# read_document — error paths
# --------------------------------------------------------------------------- #
class TestReadDocumentErrors:
    def test_unsupported_format_returns_helpful_error(self, scratch_dir):
        target = scratch_dir / "test.xyz_unknown"
        target.write_text("data", encoding="utf-8")
        result = read_document.invoke({"path": "backend/tests/_tmp_read_doc/test.xyz_unknown"})
        assert "não suportado" in result.lower()
        assert "txt" in result  # lista inclui .txt

    def test_path_outside_repo_rejected(self):
        result = read_document.invoke({"path": "/etc/passwd"})
        assert "negado" in result.lower() or "fora" in result.lower()

    def test_nonexistent_file(self):
        result = read_document.invoke({"path": "backend/tests/_nope_xyz_zzz.txt"})
        assert "não encontrado" in result.lower()

    def test_empty_file_returns_empty_message(self, scratch_dir):
        target = scratch_dir / "test_empty.txt"
        target.write_text("", encoding="utf-8")
        result = read_document.invoke({"path": "backend/tests/_tmp_read_doc/test_empty.txt"})
        assert "vazio" in result.lower() or "extraível" in result.lower()

    def test_directory_path_rejected(self):
        # `backend/tests` existe como diretório
        result = read_document.invoke({"path": "backend/tests"})
        assert any(
            phrase in result.lower()
            for phrase in ("não é um arquivo", "acesso negado", "não encontrado")
        )


# --------------------------------------------------------------------------- #
# _SUPPORTED_EXTS — não regredir acidentalmente
# --------------------------------------------------------------------------- #
class TestSupportedExts:
    def test_office_formats_included(self):
        assert "docx" in _SUPPORTED_EXTS
        assert "xlsx" in _SUPPORTED_EXTS
        assert "pptx" in _SUPPORTED_EXTS
        assert "pdf" in _SUPPORTED_EXTS

    def test_data_formats_included(self):
        assert "csv" in _SUPPORTED_EXTS
        assert "json" in _SUPPORTED_EXTS
        assert "xml" in _SUPPORTED_EXTS
        assert "html" in _SUPPORTED_EXTS

    def test_legacy_office_excluded(self):
        # .doc, .xls, .ppt não são suportados (markitdown não lida)
        assert "doc" not in _SUPPORTED_EXTS
        assert "xls" not in _SUPPORTED_EXTS
        assert "ppt" not in _SUPPORTED_EXTS
