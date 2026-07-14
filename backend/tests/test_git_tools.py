"""Rede de segurança de `src/tools/git_tools.py`.

Estas tools operam no repositório git REAL do usuário. Até a task
`unified-agent-realignment-task-floor-4` tinham ZERO testes.

Escrever a suíte revelou TRÊS FUROS DE SEGURANÇA, todos demonstrados por exploit
antes da correção, e todos derrotando o próprio sistema de tiers:

1. **O gate do `git_commit` era teatro.** `git_apply_commit` — a tool que de fato
   roda `git add` + `git commit` — não estava no `TIER_REGISTRY`, caía no default
   2 (executa direto) e commitava SEM NENHUMA aprovação humana. Bastava o modelo
   pular o `git_commit` (Tier 3) e chamar o `git_apply_commit` direto.
   (`test_git_apply_commit_requires_approval_gate`)

2. **`git_diff` (Tier 1, auto-aprovado) escrevia arquivo arbitrário.** `ref` era
   concatenado direto no argv: `git_diff(ref="--output=/qualquer/arquivo")` vira
   `git diff --output=<file>`, que ESCREVE e TRUNCA o alvo — fora do repositório,
   sem gate. (`test_git_diff_rejects_option_like_ref`)

3. **`git_branch` (Tier 1, auto-aprovado) destruía trabalho não commitado.**
   `git_branch(name="-f", checkout=True)` vira `git checkout -f`, que DESCARTA
   todas as mudanças do working tree — e a tool respondia "Agora na branch '-f'."
   (`test_git_branch_rejects_option_like_name`)

Nenhum teste toca no repositório real: `REPO_ROOT` aponta para um repo temporário.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import src.tools.git_tools as gt
import src.tools.self_extension as se


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Um repositório git temporário. Nunca toca no repo real."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init", "-q", "-b", "main"], root)
    _git(["config", "user.email", "test@test"], root)
    _git(["config", "user.name", "Test"], root)
    (root / "a.txt").write_text("v1\n")
    _git(["add", "."], root)
    _git(["commit", "-qm", "init"], root)

    def _within(p) -> bool:
        resolved = Path(p).resolve()
        return resolved == root or root in resolved.parents

    monkeypatch.setattr(gt, "REPO_ROOT", root)
    monkeypatch.setattr(se, "REPO_ROOT", root)
    monkeypatch.setattr(gt, "_within_repo", _within)
    return root


def _head(repo: Path) -> str:
    return _git(["rev-parse", "--short", "HEAD"], repo).stdout.strip()


# --------------------------------------------------------------------------- #
# FURO 1 — o gate de aprovação do commit
# --------------------------------------------------------------------------- #
def test_git_apply_commit_requires_approval_gate() -> None:
    """`git_apply_commit` é quem COMMITA — tem que estar no gate de Tier 3.

    Gatear apenas o `git_commit` (que é só um preview) deixava o bypass aberto:
    o modelo chamava `git_apply_commit` direto e commitava sem aprovação.
    """
    from src.agents.unified.tier_config import build_interrupt_on, get_tier

    assert get_tier("git_apply_commit") >= 3, (
        "git_apply_commit executa `git add` + `git commit` — não pode ter tier < 3"
    )
    assert "git_apply_commit" in build_interrupt_on(), (
        "git_apply_commit fora do interrupt_on: o gate do git_commit vira teatro, "
        "porque o modelo pode pular o preview e commitar direto."
    )


def test_git_commit_is_preview_only_and_does_not_commit(repo: Path) -> None:
    """O `git_commit` NÃO pode criar commit — ele só devolve o preview."""
    (repo / "a.txt").write_text("v2\n")
    before = _head(repo)

    out = gt.git_commit.func(message="mudanca", files=["a.txt"])

    payload = json.loads(out)
    assert payload["action"] == "preview"
    assert payload["tier"] == 3
    assert "v2" in payload["diff"]
    assert _head(repo) == before, "git_commit criou um commit — deveria só prever"


def test_git_commit_rejects_empty_message(repo: Path) -> None:
    (repo / "a.txt").write_text("v2\n")
    assert "obrigatória" in gt.git_commit.func(message="   ", files=["a.txt"])


def test_git_commit_rejects_path_outside_repo(repo: Path) -> None:
    out = gt.git_commit.func(message="m", files=["../../etc/passwd"])
    assert "Acesso negado" in out


def test_git_commit_without_staged_files_reports_nothing_to_do(repo: Path) -> None:
    out = gt.git_commit.func(message="m")
    assert "Nada a commitar" in out


def test_git_apply_commit_creates_the_commit(repo: Path) -> None:
    """Pós-aprovação, o apply de fato commita."""
    (repo / "a.txt").write_text("v2\n")
    before = _head(repo)

    out = gt.git_apply_commit.func(message="feat: v2", to_add=["a.txt"])

    assert "✅" in out
    assert _head(repo) != before
    assert _git(["log", "-1", "--pretty=%s"], repo).stdout.strip() == "feat: v2"


def test_git_apply_commit_rejects_empty_message(repo: Path) -> None:
    before = _head(repo)
    assert "obrigatória" in gt.git_apply_commit.func(message="")
    assert _head(repo) == before


# --------------------------------------------------------------------------- #
# FURO 2 — injeção de flag no `ref` do git_diff (Tier 1, sem gate)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "evil_ref",
    ["--output=/tmp/pwned.txt", "-o/tmp/pwned.txt", "--ext-diff", "--no-index"],
)
def test_git_diff_rejects_option_like_ref(repo: Path, evil_ref: str) -> None:
    out = gt.git_diff.func(ref=evil_ref)
    assert "Valor inválido" in out
    assert "opção do git" in out


def test_git_diff_output_flag_does_not_write_a_file(repo: Path, tmp_path: Path) -> None:
    """O exploit concreto: `git diff --output=<file>` escreve e TRUNCA o alvo."""
    victim = tmp_path / "FORA_DO_REPO.txt"
    assert not victim.exists()

    gt.git_diff.func(ref=f"--output={victim}")

    assert not victim.exists(), (
        "git_diff (Tier 1, auto-aprovado) escreveu um arquivo fora do repositório"
    )


def test_git_diff_shows_working_tree_changes(repo: Path) -> None:
    (repo / "a.txt").write_text("v2\n")
    out = gt.git_diff.func()
    assert "-v1" in out and "+v2" in out


def test_git_diff_clean_tree(repo: Path) -> None:
    assert "sem diferenças" in gt.git_diff.func()


def test_git_diff_rejects_path_outside_repo(repo: Path) -> None:
    assert "Acesso negado" in gt.git_diff.func(path="../../etc/passwd")


def test_git_diff_accepts_legitimate_ref(repo: Path) -> None:
    """O guard não pode quebrar o uso normal."""
    (repo / "a.txt").write_text("v2\n")
    out = gt.git_diff.func(ref="HEAD")
    assert "Valor inválido" not in out
    assert "+v2" in out


# --------------------------------------------------------------------------- #
# FURO 3 — injeção de flag no `name` do git_branch (Tier 1, sem gate)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("evil_name", ["-f", "--force", "-D", "--orphan"])
def test_git_branch_rejects_option_like_name(repo: Path, evil_name: str) -> None:
    out = gt.git_branch.func(name=evil_name, checkout=True)
    assert "Valor inválido" in out


def test_git_branch_force_checkout_does_not_destroy_work(repo: Path) -> None:
    """O exploit concreto: `git checkout -f` descarta o working tree inteiro."""
    (repo / "a.txt").write_text("TRABALHO NAO COMMITADO\n")

    gt.git_branch.func(name="-f", checkout=True)

    assert (repo / "a.txt").read_text() == "TRABALHO NAO COMMITADO\n", (
        "git_branch (Tier 1, auto-aprovado) destruiu trabalho não commitado"
    )


def test_git_branch_lists_branches(repo: Path) -> None:
    out = gt.git_branch.func()
    assert "main" in out


def test_git_branch_creates_without_checkout(repo: Path) -> None:
    out = gt.git_branch.func(name="feature-x", create=True)
    assert "criada" in out
    assert _git(["rev-parse", "--abbrev-ref", "HEAD"], repo).stdout.strip() == "main"


def test_git_branch_creates_and_checks_out(repo: Path) -> None:
    out = gt.git_branch.func(name="feature-y", create=True, checkout=True)
    assert "ativa" in out
    assert _git(["rev-parse", "--abbrev-ref", "HEAD"], repo).stdout.strip() == "feature-y"


def test_git_branch_requires_create_or_checkout(repo: Path) -> None:
    assert "inválida" in gt.git_branch.func(name="qualquer")


def test_git_branch_checkout_nonexistent_reports_error(repo: Path) -> None:
    out = gt.git_branch.func(name="nao-existe", checkout=True)
    assert "Agora na branch" not in out


# --------------------------------------------------------------------------- #
# git_status
# --------------------------------------------------------------------------- #
def test_git_status_clean_tree(repo: Path) -> None:
    out = gt.git_status.func()
    assert "Working tree limpo" in out
    assert "main" in out


def test_git_status_reports_categories(repo: Path) -> None:
    (repo / "a.txt").write_text("modificado\n")  # unstaged
    (repo / "novo.txt").write_text("novo\n")  # untracked
    (repo / "staged.txt").write_text("s\n")
    _git(["add", "staged.txt"], repo)  # staged

    payload = json.loads(gt.git_status.func())

    assert payload["branch"] == "main"
    assert payload["clean"] is False
    assert "a.txt" in payload["unstaged"]
    assert "novo.txt" in payload["untracked"]
    assert "staged.txt" in payload["staged"]


def test_git_status_no_upstream(repo: Path) -> None:
    (repo / "a.txt").write_text("x\n")
    payload = json.loads(gt.git_status.func())
    assert payload["ahead_behind"]["upstream"] is None


def test_git_status_raises_outside_git_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    not_a_repo = tmp_path / "vazio"
    not_a_repo.mkdir()
    monkeypatch.setattr(gt, "REPO_ROOT", not_a_repo)

    with pytest.raises(RuntimeError, match="não é um repositório git"):
        gt.git_status.func()
