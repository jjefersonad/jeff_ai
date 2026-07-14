"""Ferramentas de operações git nativas no repositório.

Quatro ferramentas, todas operando em `REPO_ROOT` (o repositório real sob
controle de versão), via `subprocess.run` chamando a CLI do `git`. Mantemos
o caminho do subprocess deliberadamente simples (sem `gitpython`/libgit2) para
evitar novas dependências e casar com a forma como `run_shell_command` já
funciona (Decision D5 do design).

Trilhos de segurança:

1. **Path guard** — o `path` (quando aplicável) é resolvido contra `REPO_ROOT`
   e validado por `_within_repo` para impedir escape do repositório.
2. **Option guard** (`_reject_option_like`) — valores controlados pelo modelo que
   caem em posição de argv do git (`ref`, `name`) não podem começar com '-', ou
   deixam de ser dado e viram FLAG. Ver o docstring de `_reject_option_like`:
   dois exploits reais foram demonstrados na task `floor-4` antes deste guard.
3. **Tier 1** (auto-aprovado) — `git_status`, `git_diff`, `git_branch`.
4. **Tier 3** (interrupt_on) — `git_commit` E `git_apply_commit`. Ambos, porque
   `git_apply_commit` é quem de fato commita; gatear só o `git_commit` (que é um
   mero preview) deixava o bypass aberto.

Notas:
- O tool `git_commit` NÃO commita; devolve um payload estruturado (diff +
  message + files) que o grafo apresenta via `interrupt_on`. A ação final é o
  `git_apply_commit` — que TAMBÉM é Tier 3. Em caso de rejeição, nada é alterado.
- Operamos com `cwd=REPO_ROOT` e checamos `git rev-parse --is-inside-work-tree`
  uma vez por invocação, para falhar cedo se não houver repo.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from langchain_core.tools import tool

from src.tools.self_extension import REPO_ROOT, _within_repo

# Limite defensivo para o diff inline (evita flooding do contexto do agente).
_MAX_DIFF_CHARS = int(os.getenv("GIT_DIFF_MAX_CHARS", "200_000"))
_GIT_TIMEOUT = int(os.getenv("GIT_TIMEOUT", "30"))


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _run_git(args: list[str], *, timeout: int | None = None) -> subprocess.CompletedProcess:
    """Executa `git <args>` em `REPO_ROOT` e devolve o `CompletedProcess`.

    Nunca levanta em erro do git — os callers inspecionam `returncode`/`stderr`.
    """
    proc = subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout if timeout is not None else _GIT_TIMEOUT,
    )
    return proc


def _reject_option_like(value: str, field: str) -> str | None:
    """Recusa valores que o git interpretaria como FLAG em vez de dado.

    Um valor controlado pelo modelo que começa com '-' e cai numa posição de
    argv do git deixa de ser dado e vira opção. Isso derrota o modelo de tiers:

    - `git_diff(ref="--output=/qualquer/arquivo")` → `git diff --output=<file>`
      ESCREVE (e trunca) um arquivo arbitrário. `git_diff` é Tier 1 (auto).
    - `git_branch(name="-f", checkout=True)` → `git checkout -f` → DESCARTA todo
      o trabalho não commitado. `git_branch` é Tier 1 (auto).

    Ambos foram demonstrados na task `floor-4` antes desta correção. Retorna a
    mensagem de erro se `value` for suspeito, ou None se estiver ok.
    """
    if value.startswith("-"):
        return (
            f"Valor inválido para `{field}`: {value!r} começa com '-' e seria "
            "interpretado como uma opção do git, não como um dado. "
            "Use um nome de branch/ref legítimo."
        )
    return None


def _ensure_repo() -> None:
    """Falha cedo se REPO_ROOT não for um work tree git."""
    proc = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=5,
    )
    if proc.returncode != 0 or proc.stdout.strip() != "true":
        raise RuntimeError(
            f"Diretório não é um repositório git: {REPO_ROOT}. "
            "Inicialize com `git init` ou ajuste REPO_ROOT."
        )


def _resolve_path_inside_repo(path: str | None) -> Path | None:
    """Resolve `path` (relativo ao REPO_ROOT) e garante que fica dentro do repo.

    Retorna None se `path` for None, vazio, ou se a resolução sair do repo.
    """
    if not path:
        return None
    target = (REPO_ROOT / path).resolve()
    return target if _within_repo(target) else None


def _parse_ahead_behind(branch: str) -> dict:
    """Retorna {ahead, behind, upstream} lendo @{u}, se existir."""
    proc = subprocess.run(
        ["git", "rev-list", "--left-right", "--count", f"{branch}...@{{u}}"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=10,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return {"ahead": 0, "behind": 0, "upstream": None}
    try:
        left, right = proc.stdout.strip().split()
        return {
            "ahead": int(left),
            "behind": int(right),
            "upstream": True,  # presença indica que upstream existe
        }
    except ValueError:
        return {"ahead": 0, "behind": 0, "upstream": None}


def _truncate(text: str, limit: int = _MAX_DIFF_CHARS) -> str:
    if text and len(text) > limit:
        return text[:limit] + f"\n\n[...truncado em {limit} chars...]"
    return text


# --------------------------------------------------------------------------- #
# git_status
# --------------------------------------------------------------------------- #
@tool
def git_status() -> str:
    """Mostra o estado do repositório em formato estruturado (JSON) ou legível.

    Saída JSON com chaves: `branch`, `staged[]`, `unstaged[]`, `untracked[]`,
    `ahead_behind {ahead, behind, upstream}`, `clean (bool)`. Quando o working
    tree está limpo, devolve a frase canônica: "Working tree limpo. Branch: X."
    (Tier 1 — auto-aprovado.)
    """
    _ensure_repo()

    # Branch atual (curta).
    branch_proc = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    branch = (branch_proc.stdout or "").strip() or "(detached HEAD)"

    # porcelain v1 com -z é mais robusto a paths com espaços/acentos.
    # `--untracked-files=all` faz o git descer em diretórios untracked
    # (listando cada arquivo), o que é essencial para diffs em arquivos novos.
    status_proc = _run_git(
        ["status", "--porcelain", "-z", "--untracked-files=all"]
    )
    raw = status_proc.stdout or ""

    staged: list[str] = []
    unstaged: list[str] = []
    untracked: list[str] = []

    # Cada entrada é "XY <NUL> path" (X=staged, Y=unstaged, ?=untracked).
    parts = raw.split("\x00")
    i = 0
    while i < len(parts):
        entry = parts[i]
        if not entry or len(entry) < 3:
            i += 1
            continue
        xy = entry[:2]
        path = entry[3:]
        if xy.startswith("R") or xy.startswith("C"):
            j = i + 1
            while j < len(parts) and not parts[j]:
                j += 1
            if j < len(parts):
                path = parts[j]
                i = j
        x, y = xy[0], xy[1]
        if x == "?" and y == "?":
            untracked.append(path)
        else:
            if x not in (" ", ""):
                staged.append(path)
            if y not in (" ", ""):
                unstaged.append(path)
        i += 1

    clean = not staged and not unstaged and not untracked
    payload = {
        "branch": branch,
        "staged": sorted(staged),
        "unstaged": sorted(unstaged),
        "untracked": sorted(untracked),
        "ahead_behind": _parse_ahead_behind(branch),
        "clean": clean,
    }

    if clean:
        return f"Working tree limpo. Branch: {branch}."

    return json.dumps(payload, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# git_diff
# --------------------------------------------------------------------------- #
@tool
def git_diff(ref: str = "", path: str = "") -> str:
    """Mostra um unified diff.

    - `ref` vazio: mudanças não-staged (working tree vs. index).
    - `ref="HEAD"`: mudanças staged + unstaged (working tree vs. HEAD).
    - `ref="<sha>|<branch>|<tag>"`: working tree vs. esse ref.
    - `path` opcional: restringe o diff a um arquivo/diretório dentro do repo.

    Retorna o diff bruto (possivelmente truncado para `_MAX_DIFF_CHARS`).
    (Tier 1 — auto-aprovado.)
    """
    _ensure_repo()

    if ref:
        bad = _reject_option_like(ref, "ref")
        if bad:
            return bad

    if path:
        resolved = _resolve_path_inside_repo(path)
        if resolved is None:
            return f"Acesso negado: caminho fora do repositório: {path!r}"
        rel = str(resolved.relative_to(REPO_ROOT))
    else:
        rel = ""

    args = ["diff", "--no-color", "--no-ext-diff"]
    if ref:
        args.append(ref)
    if rel:
        args.extend(["--", rel])

    proc = _run_git(args, timeout=_GIT_TIMEOUT)
    diff = proc.stdout or ""
    if not diff:
        return "(sem diferenças)" if not ref else f"(sem diferenças vs. {ref})"
    return _truncate(diff)


# --------------------------------------------------------------------------- #
# git_commit (preview, Tier 3)
# --------------------------------------------------------------------------- #
@tool
def git_commit(
    message: str,
    files: list[str] | None = None,
    *,
    auto_stage: bool = True,
) -> str:
    """Prepara um commit (com diff preview) para aprovação humana — Tier 3.

    Comportamento:
    - Valida que `message` não é vazia/branca — retorna erro sem abrir approval
      gate ("Mensagem de commit obrigatória").
    - Coleta o diff que SERÁ commitado:
        * se `files` fornecido: diff unstaged + diff cached + diff de untracked
          (via `git diff --no-index /dev/null <file>`);
        * se `files` None/vazio: commita o que já está staged (não toca no
          unstaged).
    - NÃO executa o commit aqui. Retorna payload JSON com
      `{action: "preview", message, files, diff, to_add, tier: 3}` que o grafo
      apresenta via `interrupt_on`. Após aprovação, o grafo chama
      `git_apply_commit` que efetivamente roda `git add` + `git commit -m`.
    - `auto_stage=False` reporta arquivos unstaged mas NÃO adiciona; o caller
      decide se adiciona via `git_apply_commit(to_add=[])`.
    """
    _ensure_repo()

    message = (message or "").strip()
    if not message:
        return "Mensagem de commit obrigatória."

    to_add: list[str] = []
    to_commit_diff_paths: list[str] = []

    if files:
        # 1) Validar paths dentro do repo.
        valid: list[str] = []
        for raw in files:
            resolved = _resolve_path_inside_repo(raw)
            if resolved is None:
                return f"Acesso negado: caminho fora do repositório: {raw!r}"
            if not resolved.exists():
                return f"Arquivo não encontrado: {raw}"
            valid.append(str(resolved.relative_to(REPO_ROOT)))
        files = valid

        # 2) Diff unstaged para esses arquivos.
        diff_proc = _run_git(
            ["diff", "--no-color", "--no-ext-diff", "--", *files]
        )
        unstaged_diff = diff_proc.stdout or ""

        # 3) Diff já em stage (cached) por arquivo.
        staged_diff_parts: list[str] = []
        for f in files:
            sp = _run_git(
                ["diff", "--cached", "--no-color", "--no-ext-diff", "--", f]
            )
            if sp.stdout:
                staged_diff_parts.append(sp.stdout)
        staged_diff = "\n".join(staged_diff_parts)

        # 4) Diff para arquivos untracked: `git diff` não emite nada, então
        # usamos `git diff --no-index -- /dev/null <file>` para mostrar o
        # conteúdo completo como adições.
        porcelain = _run_git(
            ["status", "--porcelain", "-z", "--untracked-files=all"]
        ).stdout or ""
        untracked_set: set[str] = set()
        for entry in porcelain.split("\x00"):
            if not entry or len(entry) < 3:
                continue
            if entry[:2] == "??":
                untracked_set.add(entry[3:])
        untracked_diff_parts: list[str] = []
        for f in files:
            if f in untracked_set:
                up = _run_git(
                    ["diff", "--no-color", "--no-index", "--no-ext-diff",
                     "--", "/dev/null", f]
                )
                if up.stdout:
                    untracked_diff_parts.append(up.stdout)
        untracked_diff = "\n".join(untracked_diff_parts)

        # Diff final: staged + unstaged + untracked.
        parts = [staged_diff, unstaged_diff, untracked_diff]
        final_diff = "\n".join(p for p in parts if p)

        if auto_stage:
            to_add = list(files)
        to_commit_diff_paths = list(files)
    else:
        # Sem `files`: commita o que já está staged.
        staged_proc = _run_git(
            ["diff", "--cached", "--name-only", "--no-color"]
        )
        names = [
            ln.strip()
            for ln in (staged_proc.stdout or "").splitlines()
            if ln.strip()
        ]
        to_commit_diff_paths = names
        diff_proc = _run_git(
            ["diff", "--cached", "--no-color", "--no-ext-diff"]
        )
        final_diff = diff_proc.stdout or ""
        if not names:
            return (
                "Nada a commitar: nenhum arquivo staged. "
                "Forneça `files=[...]` ou rode `git add` antes."
            )

    payload = {
        "action": "preview",
        "message": message,
        "files": to_commit_diff_paths,
        "to_add": to_add,
        "diff": _truncate(final_diff or "(sem diff)"),
        "tier": 3,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# git_apply_commit (helper pós-aprovação)
# --------------------------------------------------------------------------- #
@tool
def git_apply_commit(
    message: str,
    files: list[str] | None = None,
    to_add: list[str] | None = None,
) -> str:
    """Executa o commit após a aprovação humana (Tier 3 → ação).

    Recebe o payload validado pelo `git_commit` (preview) e aplica:
    1. `git add <to_add>` se houver itens para stagear.
    2. `git commit -m <message>`.

    Retorna SHA curto + mensagem de sucesso, ou mensagem de erro do git.
    """
    _ensure_repo()
    message = (message or "").strip()
    if not message:
        return "Mensagem de commit obrigatória."

    if to_add:
        proc = _run_git(["add", "--", *to_add])
        if proc.returncode != 0:
            return (proc.stderr or proc.stdout or "").strip() or "Falha no `git add`."

    proc = _run_git(["commit", "-m", message])
    if proc.returncode != 0:
        out = (proc.stderr or proc.stdout or "").strip()
        return f"Falha no `git commit`: {out or '(sem mensagem)'}"

    sha_proc = _run_git(["rev-parse", "--short", "HEAD"])
    short_sha = (sha_proc.stdout or "").strip()
    return f"✅ Commit {short_sha} criado: \"{message}\" ({len(files or to_add or [])} arquivo(s))."


# --------------------------------------------------------------------------- #
# git_branch
# --------------------------------------------------------------------------- #
@tool
def git_branch(
    name: str = "",
    create: bool = False,
    checkout: bool = False,
) -> str:
    """Gerencia branches locais.

    - Sem argumentos: lista as branches locais, marcando a atual com `*`.
    - `name="X", create=True, checkout=False`: cria `X` mas não muda para ela.
    - `name="X", checkout=True, create=False`: faz `git checkout X`.
    - `name="X", create=True, checkout=True`: faz `git checkout -b X`.
    - `name="X", create=False, checkout=False`: erro (não é operação válida).
    """
    _ensure_repo()

    if not name:
        proc = _run_git(["branch", "--no-color"])
        out = (proc.stdout or "").strip()
        if not out:
            return "(nenhuma branch local)"
        return out

    bad = _reject_option_like(name, "name")
    if bad:
        return bad

    if not create and not checkout:
        return (
            "Operação inválida: para 'git_branch(name=X)' use pelo menos "
            "`create=True` ou `checkout=True`."
        )

    if create and not checkout:
        proc = _run_git(["branch", name])
        if proc.returncode != 0:
            return (proc.stderr or proc.stdout or "").strip() or "Falha ao criar branch."
        return f"Branch '{name}' criada (não ativa)."

    if create and checkout:
        proc = _run_git(["checkout", "-b", name])
        if proc.returncode != 0:
            return (proc.stderr or proc.stdout or "").strip() or "Falha ao criar e trocar para a branch."
        return f"Branch '{name}' criada e ativa."

    proc = _run_git(["checkout", name])
    if proc.returncode != 0:
        return (proc.stderr or proc.stdout or "").strip() or "Falha ao trocar de branch."
    return f"Agora na branch '{name}'."
