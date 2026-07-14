"""Rede de segurança de `src/tools/code_editing_tools.py`.

Estas tools ESCREVEM no repositório real do usuário (Tier 3). Até a task
`unified-agent-realignment-task-floor-3` elas tinham ZERO testes — o design da
`unified-dev-agent` classificava o risco R2 ("code-editing tools corrupt the real
repository") como Critical e listava os testes como mitigação; a task foi
arquivada sem eles.

Escrever a suíte revelou três defeitos reais, cada um travado por um teste aqui:

1. `edit_file` com `old_string` ambíguo editava a PRIMEIRA das N ocorrências e
   retornava "[OK]" — escolhendo pelo chamador e possivelmente editando o lugar
   errado. Agora é erro. (`test_edit_file_ambiguous_*`)
2. `_atomic_write` destruía o modo do arquivo: `mkstemp` cria 0600 e `os.replace`
   leva esse modo junto. Editar um script `0755` o deixava não-executável.
   (`test_atomic_write_preserves_mode`)
3. `multi_file_edit` com duas edições no MESMO arquivo calculava ambas sobre o
   conteúdo original; a segunda escrita descartava a primeira — silenciosamente,
   reportando "[OK] 2 edições aplicadas". (`test_multi_file_edit_same_file_*`)

Nenhum teste toca no repositório real: `REPO_ROOT` é remapeado para um tmpdir.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import src.tools.code_editing_tools as ce
import src.tools.self_extension as se


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Um REPO_ROOT falso, isolado. Nunca toca no repositório real."""
    root = tmp_path / "repo"
    root.mkdir()

    def _within(p) -> bool:
        resolved = Path(p).resolve()
        return resolved == root or root in resolved.parents

    monkeypatch.setattr(ce, "REPO_ROOT", root)
    monkeypatch.setattr(se, "REPO_ROOT", root)
    monkeypatch.setattr(ce, "_within_repo", _within)
    return root


def _edit(**kw) -> str:
    return ce.edit_file.func(**kw)


def _multi(edits: list[dict]) -> str:
    return ce.multi_file_edit.func(edits=edits)


def _patch(**kw) -> str:
    return ce.patch_file.func(**kw)


def _grep(**kw) -> str:
    return ce.grep_project.func(**kw)


# --------------------------------------------------------------------------- #
# edit_file
# --------------------------------------------------------------------------- #
def test_edit_file_replaces_unique_occurrence(repo: Path) -> None:
    f = repo / "a.py"
    f.write_text("alpha = 1\nbeta = 2\n")

    out = _edit(path="a.py", old_string="alpha = 1", new_string="alpha = 99")

    assert "[OK]" in out
    assert f.read_text() == "alpha = 99\nbeta = 2\n"


def test_edit_file_ambiguous_old_string_does_not_write(repo: Path) -> None:
    """DEFEITO 1: N>1 ocorrências deve FALHAR, não editar a primeira."""
    f = repo / "a.py"
    original = "x = 1\nx = 1\nx = 1\n"
    f.write_text(original)

    out = _edit(path="a.py", old_string="x = 1", new_string="x = 2")

    assert "[SEM ALTERAÇÃO]" in out
    assert "3x" in out, "o erro deve dizer quantas ocorrências foram encontradas"
    assert f.read_text() == original, "o arquivo NÃO pode ser modificado"


def test_edit_file_ambiguity_resolved_by_context(repo: Path) -> None:
    """A saída do erro ambíguo é acionável: dar contexto resolve."""
    f = repo / "a.py"
    f.write_text("x = 1\ny = 0\nx = 1\n")

    out = _edit(path="a.py", old_string="y = 0\nx = 1", new_string="y = 0\nx = 2")

    assert "[OK]" in out
    assert f.read_text() == "x = 1\ny = 0\nx = 2\n"


def test_edit_file_missing_old_string_does_not_write(repo: Path) -> None:
    f = repo / "a.py"
    original = "alpha = 1\n"
    f.write_text(original)

    out = _edit(path="a.py", old_string="nao_existe", new_string="qualquer")

    assert "[SEM ALTERAÇÃO]" in out
    assert f.read_text() == original


def test_edit_file_missing_file(repo: Path) -> None:
    out = _edit(path="fantasma.py", old_string="a", new_string="b")
    assert "não encontrado" in out.lower()


# --------------------------------------------------------------------------- #
# Escrita atômica
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(os.name == "nt", reason="modos POSIX")
def test_atomic_write_preserves_mode(repo: Path) -> None:
    """DEFEITO 2: editar um script executável não pode tirar o bit de execução."""
    sh = repo / "run.sh"
    sh.write_text("#!/bin/sh\necho oi\n")
    sh.chmod(0o755)

    out = _edit(path="run.sh", old_string="echo oi", new_string="echo tchau")

    assert "[OK]" in out
    assert sh.stat().st_mode & 0o777 == 0o755, "o modo do arquivo foi destruído"
    assert os.access(sh, os.X_OK), "o arquivo deixou de ser executável"


def test_atomic_write_leaves_no_temp_files(repo: Path) -> None:
    f = repo / "a.py"
    f.write_text("alpha = 1\n")

    _edit(path="a.py", old_string="alpha = 1", new_string="alpha = 2")

    assert not list(repo.glob("*.tmp")), "sobrou arquivo temporário"


# --------------------------------------------------------------------------- #
# Limite do repositório (path traversal)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "escape",
    ["../../etc/passwd", "/etc/passwd", "../fora.txt", "sub/../../../fora.txt"],
)
def test_edit_file_refuses_paths_outside_repo(repo: Path, escape: str) -> None:
    out = _edit(path=escape, old_string="root", new_string="pwned")
    assert "Acesso negado" in out


def test_multi_file_edit_refuses_paths_outside_repo(repo: Path) -> None:
    f = repo / "a.py"
    f.write_text("alpha = 1\n")

    out = _multi(
        [
            {"path": "a.py", "old_string": "alpha = 1", "new_string": "alpha = 2"},
            {"path": "../../etc/passwd", "old_string": "root", "new_string": "x"},
        ]
    )

    assert "[LOTE REJEITADO]" in out
    assert f.read_text() == "alpha = 1\n", "a edição válida do lote não pode vazar"


# --------------------------------------------------------------------------- #
# multi_file_edit — all-or-nothing
# --------------------------------------------------------------------------- #
def test_multi_file_edit_applies_all_valid(repo: Path) -> None:
    a, b = repo / "a.py", repo / "b.py"
    a.write_text("alpha = 1\n")
    b.write_text("beta = 2\n")

    out = _multi(
        [
            {"path": "a.py", "old_string": "alpha = 1", "new_string": "alpha = 99"},
            {"path": "b.py", "old_string": "beta = 2", "new_string": "beta = 88"},
        ]
    )

    assert "[OK]" in out
    assert a.read_text() == "alpha = 99\n"
    assert b.read_text() == "beta = 88\n"


def test_multi_file_edit_one_invalid_applies_none(repo: Path) -> None:
    """All-or-nothing: uma edição inválida no lote não pode deixar as outras passarem."""
    a, b = repo / "a.py", repo / "b.py"
    a.write_text("alpha = 1\n")
    b.write_text("beta = 2\n")

    out = _multi(
        [
            {"path": "a.py", "old_string": "alpha = 1", "new_string": "alpha = 99"},
            {"path": "b.py", "old_string": "NAO_EXISTE", "new_string": "x"},
        ]
    )

    assert "[LOTE REJEITADO]" in out
    assert a.read_text() == "alpha = 1\n", "NENHUMA edição pode ser aplicada"
    assert b.read_text() == "beta = 2\n"


def test_multi_file_edit_same_file_accumulates_edits(repo: Path) -> None:
    """DEFEITO 3: duas edições no mesmo arquivo não podem se sobrescrever."""
    f = repo / "b.py"
    f.write_text("alpha = 1\nbeta = 2\n")

    out = _multi(
        [
            {"path": "b.py", "old_string": "alpha = 1", "new_string": "alpha = 99"},
            {"path": "b.py", "old_string": "beta = 2", "new_string": "beta = 88"},
        ]
    )

    assert "[OK]" in out
    final = f.read_text()
    assert "alpha = 99" in final, "a PRIMEIRA edição foi silenciosamente descartada"
    assert "beta = 88" in final
    assert final == "alpha = 99\nbeta = 88\n"


def test_multi_file_edit_same_file_second_edit_sees_first(repo: Path) -> None:
    """Uma edição no lote pode depender do resultado da anterior."""
    f = repo / "b.py"
    f.write_text("valor = 1\n")

    out = _multi(
        [
            {"path": "b.py", "old_string": "valor = 1", "new_string": "valor = 2"},
            {"path": "b.py", "old_string": "valor = 2", "new_string": "valor = 3"},
        ]
    )

    assert "[OK]" in out
    assert f.read_text() == "valor = 3\n"


def test_multi_file_edit_rejects_ambiguous_old_string(repo: Path) -> None:
    f = repo / "a.py"
    original = "x = 1\nx = 1\n"
    f.write_text(original)

    out = _multi([{"path": "a.py", "old_string": "x = 1", "new_string": "x = 2"}])

    assert "[LOTE REJEITADO]" in out
    assert f.read_text() == original


def test_multi_file_edit_rejects_malformed_edit(repo: Path) -> None:
    f = repo / "a.py"
    f.write_text("alpha = 1\n")

    out = _multi([{"path": "a.py", "old_string": "alpha = 1"}])  # falta new_string

    assert "[LOTE REJEITADO]" in out
    assert f.read_text() == "alpha = 1\n"


def test_multi_file_edit_empty_list(repo: Path) -> None:
    assert "Nenhuma edição" in _multi([])


# --------------------------------------------------------------------------- #
# patch_file
# --------------------------------------------------------------------------- #
def test_patch_file_applies_valid_diff(repo: Path) -> None:
    f = repo / "a.py"
    f.write_text("um\ndois\ntres\n")

    diff = "@@ -1,3 +1,3 @@\n um\n-dois\n+DOIS\n tres\n"
    out = _patch(path="a.py", diff_text=diff)

    assert "[OK]" in out
    assert f.read_text() == "um\nDOIS\ntres\n"


def test_patch_file_rejects_non_matching_hunk(repo: Path) -> None:
    f = repo / "a.py"
    original = "um\ndois\ntres\n"
    f.write_text(original)

    # O hunk afirma que a linha 2 é "OUTRA COISA" — não casa.
    diff = "@@ -1,3 +1,3 @@\n um\n-OUTRA COISA\n+DOIS\n tres\n"
    out = _patch(path="a.py", diff_text=diff)

    assert "[PATCH REJEITADO]" in out
    assert f.read_text() == original, "o arquivo não pode ser tocado"


def test_patch_file_rejects_malformed_diff(repo: Path) -> None:
    f = repo / "a.py"
    original = "um\n"
    f.write_text(original)

    out = _patch(path="a.py", diff_text="isso nao e um diff")

    assert "[PATCH INVÁLIDO]" in out
    assert f.read_text() == original


def test_patch_file_rejects_hunk_past_eof(repo: Path) -> None:
    f = repo / "a.py"
    original = "um\n"
    f.write_text(original)

    diff = "@@ -50,1 +50,1 @@\n-um\n+dois\n"
    out = _patch(path="a.py", diff_text=diff)

    assert "[PATCH REJEITADO]" in out
    assert f.read_text() == original


def test_patch_file_refuses_path_outside_repo(repo: Path) -> None:
    out = _patch(path="../../etc/passwd", diff_text="@@ -1,1 +1,1 @@\n-a\n+b\n")
    assert "Acesso negado" in out


@pytest.mark.skipif(os.name == "nt", reason="modos POSIX")
def test_patch_file_preserves_mode(repo: Path) -> None:
    sh = repo / "run.sh"
    sh.write_text("um\ndois\n")
    sh.chmod(0o755)

    _patch(path="run.sh", diff_text="@@ -1,2 +1,2 @@\n um\n-dois\n+DOIS\n")

    assert sh.stat().st_mode & 0o777 == 0o755


# --------------------------------------------------------------------------- #
# grep_project
# --------------------------------------------------------------------------- #
def test_grep_finds_matches(repo: Path) -> None:
    (repo / "a.py").write_text("def alvo():\n    pass\n")

    out = _grep(pattern=r"def alvo", path=".", include="*.py")

    assert "a.py:1" in out


def test_grep_invalid_regex_does_not_raise(repo: Path) -> None:
    (repo / "a.py").write_text("x\n")
    assert "Regex inválida" in _grep(pattern="[abc", path=".", include="*.py")


def test_grep_skips_binary_files(repo: Path) -> None:
    (repo / "bin.dat").write_bytes(b"alvo\x00\x01\x02alvo")

    out = _grep(pattern="alvo", path=".", include="*")

    assert "bin.dat" not in out
    assert "pulado" in out


def test_grep_skips_large_files(repo: Path) -> None:
    big = repo / "big.py"
    big.write_text("alvo\n" + ("x" * (ce._MAX_FILE_BYTES + 10)))

    out = _grep(pattern="alvo", path=".", include="*.py")

    assert "big.py" not in out


def test_grep_truncates_at_limit(repo: Path) -> None:
    (repo / "a.py").write_text("alvo\n" * (ce._GREP_MAX_RESULTS + 20))

    out = _grep(pattern="alvo", path=".", include="*.py")

    assert "limitado a" in out
    assert out.count("a.py:") == ce._GREP_MAX_RESULTS


def test_grep_refuses_path_outside_repo(repo: Path) -> None:
    assert "Acesso negado" in _grep(pattern="root", path="../../etc", include="*")
