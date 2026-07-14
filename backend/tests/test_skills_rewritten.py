"""Testes que as skills foram reescritas para apontar às tools nativas.

Cobrem os critérios de aceitação da task `custom-office-doc-tools-task-integration-2`:
- REQ-004 (docx/xlsx/pptx): `backend/skills/{docx,xlsx,pptx}/SKILL.md` instruem
  usar as tools nativas; não referenciam pandoc/soffice/docx-js/pptxgenjs/
  markitdown como caminho principal de geração.
- Scripts `scripts/office/*` (e auxiliares) marcados como legados.
- `CLAUDE.md` menciona as novas tools de documento e a rota `/api/files`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = REPO_ROOT / "backend" / "skills"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"


# --- helpers ---------------------------------------------------------------


def _read(path: Path) -> str:
    """Lê um arquivo como texto (utf-8) — falha alto se não existir."""
    assert path.is_file(), f"Arquivo esperado não existe: {path}"
    return path.read_text(encoding="utf-8")


# --- REQ-004: skills instruem usar tools nativas ---------------------------


@pytest.mark.parametrize(
    ("skill", "tool_name", "lib"),
    [
        ("docx", "create_docx_document", "python-docx"),
        ("xlsx", "create_xlsx_spreadsheet", "openpyxl"),
        ("pptx", "create_pptx_presentation", "python-pptx"),
    ],
)
def test_skill_points_to_native_tool(skill: str, tool_name: str, lib: str):
    """A SKILL.md da skill instrui usar a tool nativa e cita a lib."""
    content = _read(SKILLS_DIR / skill / "SKILL.md")
    assert tool_name in content, (
        f"{skill}/SKILL.md não menciona a tool {tool_name!r}"
    )
    assert lib in content, f"{skill}/SKILL.md não menciona a lib {lib!r}"


@pytest.mark.parametrize("skill", ["docx", "xlsx", "pptx"])
def test_skill_does_not_recommend_external_binaries_as_main_path(skill: str):
    """A SKILL.md não recomenda pandoc/soffice/docx-js/pptxgenjs/markitdown."""
    raw = _read(SKILLS_DIR / skill / "SKILL.md")
    # Exclui o frontmatter (entre o primeiro par de `---`) — lá o "Use this skill"
    # é apenas descritivo, não uma instrução de uso.
    parts = raw.split("---", 2)
    content = parts[2] if len(parts) >= 3 else raw

    forbidden = ("pandoc", "soffice", "libreoffice", "docx-js", "pptxgenjs", "markitdown")
    for keyword in forbidden:
        # Padrões que indicam recomendação ativa (não simples menção histórica).
        active_patterns = [
            rf"Use\s+{keyword}\b",                # "Use soffice" / "Use pandoc"
            rf"npm\s+install[^\n]*{keyword}\b",
            rf"pip\s+install[^\n]*{keyword}\b",
            rf"Install:[^\n]*{keyword}\b",
            rf"Instale[^\n]*{keyword}\b",          # português
        ]
        for pat in active_patterns:
            assert not re.search(pat, content, re.IGNORECASE), (
                f"{skill}/SKILL.md recomenda ativamente {keyword!r} "
                f"(regex: {pat!r})"
            )


# --- Limitações documentadas -----------------------------------------------


@pytest.mark.parametrize("skill", ["docx", "xlsx", "pptx"])
def test_skill_documents_creation_only_limitation(skill: str):
    """A SKILL.md declara explicitamente que o escopo é só criação."""
    content = _read(SKILLS_DIR / skill / "SKILL.md").lower()
    assert "criação" in content or "criar" in content or "create" in content
    # Procura por uma das palavras-chave que marcam a limitação.
    assert (
        "fora do escopo" in content
        or "out of scope" in content
        or "escopo desta" in content
    ), f"{skill}/SKILL.md não documenta a limitação de escopo (criação only)."


# --- Scripts `office/*` marcados como legados -----------------------------


@pytest.mark.parametrize("skill", ["docx", "xlsx", "pptx"])
def test_office_scripts_marked_as_legacy(skill: str):
    """`scripts/office/README.md` marca o diretório como legado."""
    readme = SKILLS_DIR / skill / "scripts" / "office" / "README.md"
    assert readme.is_file(), f"Esperado {readme} (avisando sobre legado)."
    content = _read(readme)
    assert "LEGADO" in content or "legado" in content, (
        f"{readme} não marca o conteúdo como legado."
    )


@pytest.mark.parametrize("skill", ["docx", "xlsx", "pptx"])
def test_top_level_scripts_have_legacy_notice(skill: str):
    """`scripts/README.md` (top-level) explica que tudo é legado."""
    readme = SKILLS_DIR / skill / "scripts" / "README.md"
    assert readme.is_file(), f"Esperado {readme} (avisando sobre scripts legados)."
    content = _read(readme)
    assert "aposentado" in content.lower() or "legado" in content.lower(), (
        f"{readme} não marca os scripts top-level como aposentados."
    )


# --- CLAUDE.md menciona as tools e a rota ---------------------------------


def test_claude_md_documents_office_tools():
    """`CLAUDE.md` cita as 3 tools nativas e a rota `/api/files`."""
    content = _read(CLAUDE_MD)
    assert "create_docx_document" in content
    assert "create_xlsx_spreadsheet" in content
    assert "create_pptx_presentation" in content
    assert "/api/files" in content, "CLAUDE.md não menciona a rota /api/files."


def test_claude_md_documents_native_libs():
    """`CLAUDE.md` cita as bibliotecas nativas (python-docx, openpyxl, python-pptx)."""
    content = _read(CLAUDE_MD)
    for lib in ("python-docx", "openpyxl", "python-pptx"):
        assert lib in content, f"CLAUDE.md não menciona a lib {lib!r}."
