"""Rede de segurança de `src/tools/test_runner_tools.py`.

`run_tests` é Tier 1 (auto-aprovado) e executa um subprocess. Até a task
`unified-agent-realignment-task-floor-4` tinha ZERO testes.

Diferente de `code_editing_tools` e `git_tools`, a auditoria não encontrou furos
aqui: `_resolve_test_path` valida contra `REPO_ROOT` antes de qualquer execução,
e um valor tipo flag (`-x`, `--co`) não resolve para um caminho existente, então
é recusado antes de chegar ao argv do pytest. Estes testes travam essa
propriedade — que é o que impede o `run_tests` de virar um `run_shell_command`
sem gate.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import src.tools.self_extension as se
import src.tools.test_runner_tools as tr


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """REPO_ROOT/BACKEND_DIR falsos com uma mini-suíte dentro."""
    root = tmp_path / "repo"
    backend = root / "backend"
    tests = backend / "tests"
    tests.mkdir(parents=True)
    (backend / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")

    def _within(p) -> bool:
        resolved = Path(p).resolve()
        return resolved == root or root in resolved.parents

    monkeypatch.setattr(tr, "REPO_ROOT", root)
    monkeypatch.setattr(tr, "BACKEND_DIR", backend)
    monkeypatch.setattr(se, "REPO_ROOT", root)
    monkeypatch.setattr(tr, "_within_repo", _within)
    return backend


def _run(**kw) -> str:
    return tr.run_tests.func(**kw)


# --------------------------------------------------------------------------- #
# Guard de caminho — o que impede run_tests de virar shell sem gate
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("escape", ["../../etc", "/etc/passwd", "../fora"])
def test_run_tests_refuses_paths_outside_repo(fake_repo: Path, escape: str) -> None:
    out = _run(test_path=escape)
    assert "Acesso negado" in out or "não encontrado" in out.lower()


@pytest.mark.parametrize("flag", ["-x", "--collect-only", "-p", "--co"])
def test_run_tests_does_not_accept_pytest_flags_as_path(fake_repo: Path, flag: str) -> None:
    """Uma flag não pode chegar ao argv do pytest via `test_path`."""
    out = _run(test_path=flag)
    assert "não encontrado" in out.lower() or "Acesso negado" in out


def test_run_tests_missing_path(fake_repo: Path) -> None:
    assert "não encontrado" in _run(test_path="tests/nao_existe.py").lower()


# --------------------------------------------------------------------------- #
# Execução real
# --------------------------------------------------------------------------- #
def test_run_tests_all_passing(fake_repo: Path) -> None:
    (fake_repo / "tests" / "test_ok.py").write_text(
        "def test_um():\n    assert True\n\ndef test_dois():\n    assert 1 + 1 == 2\n"
    )

    out = _run(test_path="tests")

    assert "✅" in out
    assert "2" in out


def test_run_tests_reports_failure_with_location(fake_repo: Path) -> None:
    (fake_repo / "tests" / "test_falha.py").write_text(
        "def test_ok():\n    assert True\n\ndef test_quebra():\n    assert 1 == 2\n"
    )

    out = _run(test_path="tests")

    assert "❌" in out
    assert "test_quebra" in out
    assert "1 passaram" in out or "✅ 1" in out


def test_run_tests_reports_skipped(fake_repo: Path) -> None:
    (fake_repo / "tests" / "test_skip.py").write_text(
        "import pytest\n\n@pytest.mark.skip(reason='x')\ndef test_pulado():\n    pass\n"
    )

    out = _run(test_path="tests")

    assert "⏭️" in out or "ignorados" in out


def test_run_tests_collection_error_is_reported_not_raised(fake_repo: Path) -> None:
    """Erro de import não pode estourar exceção — tem que virar mensagem."""
    (fake_repo / "tests" / "test_import_ruim.py").write_text(
        "import modulo_que_nao_existe_xyz\n\ndef test_x():\n    pass\n"
    )

    out = _run(test_path="tests")

    assert "❌" in out
    assert isinstance(out, str)


def test_run_tests_empty_directory(fake_repo: Path) -> None:
    out = _run(test_path="tests")
    assert "não encontrado" in out.lower() or "sem testes" in out.lower()


def test_run_tests_single_file(fake_repo: Path) -> None:
    (fake_repo / "tests" / "test_solo.py").write_text("def test_a():\n    assert True\n")

    out = _run(test_path="tests/test_solo.py")

    assert "✅" in out


# --------------------------------------------------------------------------- #
# Truncamento — o traceback não pode inundar o contexto do modelo
# --------------------------------------------------------------------------- #
def test_traceback_is_truncated_keeping_the_tail() -> None:
    """A cauda do traceback é o que importa (onde está a asserção que falhou)."""
    long_tb = "\n".join(f"linha {i}" for i in range(200))

    out = tr._truncate_traceback(long_tb)

    assert out.startswith("[...]")
    assert "linha 199" in out, "a cauda foi descartada"
    assert "linha 0" not in out
    assert len(out.splitlines()) <= tr._TB_MAX_LINES + 1


def test_short_traceback_is_not_truncated() -> None:
    out = tr._truncate_traceback("a\nb\nc")
    assert out == "a\nb\nc"
    assert "[...]" not in out


# --------------------------------------------------------------------------- #
# Detecção de framework
# --------------------------------------------------------------------------- #
def test_detect_framework_defaults_to_pytest(fake_repo: Path) -> None:
    assert tr._detect_framework() == "pytest"


def test_unknown_framework_falls_back_to_pytest(fake_repo: Path) -> None:
    (fake_repo / "tests" / "test_ok.py").write_text("def test_a():\n    assert True\n")

    out = _run(test_path="tests", framework="jest")

    assert "✅" in out, "framework desconhecido deve cair no pytest, não quebrar"
