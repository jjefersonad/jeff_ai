"""Ferramentas de auto-extensão do assistant.

Três capacidades, todas com trilhos de segurança:

1. LEITURA do repositório (somente leitura) — `list_project_files`, `read_project_file`.
   Permite ao assistant analisar a própria arquitetura sem poder alterar código.

2. Criação de FERRAMENTAS Python com GATE humano — `save_generated_tool`,
   `list_generated_tools` + o loader `load_approved_tools`.
   O assistant escreve o módulo em `src/tools/generated/` (staging). A ferramenta só é
   carregada no grafo se um humano aprovar (listando-a em `approved.json`) e reiniciar.
   Não há hot-load: código novo só entra na próxima subida do servidor.

Obs.: a criação de SKILLS (markdown) não precisa deste módulo — o assistant já tem
escrita na rota `/skills/` e as skills são carregadas em runtime pelo deepagents.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from langchain_core.tools import BaseTool, tool

_THIS = Path(__file__).resolve()
BACKEND_DIR = _THIS.parents[2]
REPO_ROOT = _THIS.parents[3]
GENERATED_DIR = BACKEND_DIR / "src" / "tools" / "generated"
APPROVED_MANIFEST = GENERATED_DIR / "approved.json"
SKILLS_DIR = BACKEND_DIR / "skills"

# Repositórios permitidos para instalação de skills externas (`npx skills add`).
# Pode ser estendida via env SKILLS_ALLOWLIST (lista separada por vírgula).
_DEFAULT_SKILL_REPOS = {
    "vercel-labs/skills",
    "https://github.com/vercel-labs/skills",
}

# Diretórios pesados/irrelevantes que não devem ser listados/lidos.
_IGNORE = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".next",
    ".mypy_cache", ".ruff_cache", "dist", "build", ".pytest_cache",
}
_MAX_READ_CHARS = 200_000


def _within_repo(target: Path) -> bool:
    """Retorna True se `target` está dentro da raiz do repositório."""
    return target == REPO_ROOT or REPO_ROOT in target.parents


# --------------------------------------------------------------------------- #
# 1. Leitura do repositório (somente leitura)
# --------------------------------------------------------------------------- #
@tool
def list_project_files(subdir: str = ".") -> str:
    """Lista arquivos e pastas do repositório (SOMENTE LEITURA).

    Use para navegar o código e analisar a arquitetura do próprio projeto.
    `subdir` é relativo à raiz do repo (ex.: 'backend/src/agents'). Não permite
    sair da raiz do repositório.
    """
    target = (REPO_ROOT / subdir).resolve()
    if not _within_repo(target):
        return "Acesso negado: caminho fora do repositório."
    if not target.exists():
        return f"Não encontrado: {subdir}"
    if target.is_file():
        return f"'{subdir}' é um arquivo. Use read_project_file para ler o conteúdo."
    entries = []
    for e in sorted(target.iterdir()):
        if e.name in _IGNORE:
            continue
        prefix = "[dir] " if e.is_dir() else "      "
        entries.append(f"{prefix}{e.relative_to(REPO_ROOT)}")
    return "\n".join(entries) or "(diretório vazio)"


@tool
def read_project_file(path: str) -> str:
    """Lê o conteúdo de um arquivo do repositório (SOMENTE LEITURA).

    `path` é relativo à raiz do repo (ex.: 'backend/langgraph.json'). Não permite
    ler fora da raiz do repositório. Conteúdo é truncado se muito grande.
    """
    target = (REPO_ROOT / path).resolve()
    if not _within_repo(target):
        return "Acesso negado: caminho fora do repositório."
    if not target.is_file():
        return f"Arquivo não encontrado: {path}"
    data = target.read_text(encoding="utf-8", errors="replace")
    if len(data) > _MAX_READ_CHARS:
        return data[:_MAX_READ_CHARS] + "\n\n[...truncado...]"
    return data


# --------------------------------------------------------------------------- #
# 2. Criação de ferramentas Python com gate humano
# --------------------------------------------------------------------------- #
def _read_approved() -> list[str]:
    """Lê a lista de módulos aprovados de approved.json (robusto a erros)."""
    if not APPROVED_MANIFEST.exists():
        return []
    try:
        data = json.loads(APPROVED_MANIFEST.read_text(encoding="utf-8"))
        return [str(x) for x in data] if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


@tool
def save_generated_tool(filename: str, code: str) -> str:
    """Escreve um NOVO módulo de ferramenta Python em staging (não ativa nada).

    O módulo deve definir uma ou mais funções decoradas com @tool
    (de langchain_core.tools). Ele fica em `src/tools/generated/<filename>` e só
    entra em uso após: (1) revisão humana do código, (2) inclusão do nome em
    `src/tools/generated/approved.json`, (3) reinício do backend. NÃO há hot-load.
    """
    if not re.fullmatch(r"[a-zA-Z0-9_]+\.py", filename):
        return "filename inválido. Use apenas letras, números e '_', terminando em '.py'."
    if filename == "__init__.py":
        return "Nome reservado. Escolha outro nome."
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    (GENERATED_DIR / filename).write_text(code, encoding="utf-8")
    return (
        f"Ferramenta salva em staging: src/tools/generated/{filename}\n"
        "STATUS: NÃO ATIVA (pendente de aprovação).\n"
        "Para ativar, um humano precisa: (1) revisar o código, "
        f"(2) adicionar \"{filename}\" à lista em src/tools/generated/approved.json, "
        "(3) reiniciar o backend."
    )


@tool
def list_generated_tools() -> str:
    """Lista as ferramentas Python geradas em staging e seu status de aprovação."""
    if not GENERATED_DIR.exists():
        return "Nenhuma ferramenta gerada ainda."
    approved = _read_approved()
    lines = []
    for f in sorted(GENERATED_DIR.glob("*.py")):
        if f.name == "__init__.py":
            continue
        status = "APROVADA" if f.name in approved else "pendente"
        lines.append(f"- {f.name} [{status}]")
    return "\n".join(lines) or "Nenhuma ferramenta gerada ainda."


def load_approved_tools() -> list[BaseTool]:
    """Importa e retorna as ferramentas aprovadas de src/tools/generated/.

    Chamado no build do grafo do assistant. É robusto: nunca levanta exceção —
    módulos com erro são apenas ignorados (com log), para não quebrar o servidor.
    """
    loaded: list[BaseTool] = []
    for name in _read_approved():
        path = GENERATED_DIR / name
        if not path.is_file():
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"generated_{path.stem}", path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for value in vars(module).values():
                if isinstance(value, BaseTool):
                    loaded.append(value)
        except Exception as exc:  # noqa: BLE001 - nunca deve quebrar o build
            print(f"[self_extension] falha ao carregar tool aprovada '{name}': {exc}")  # noqa: T201
    return loaded


# --------------------------------------------------------------------------- #
# 3. Instalação de skills externas (RESTRITA por allowlist)
# --------------------------------------------------------------------------- #
def _allowed_skill_repos() -> set[str]:
    """Allowlist de repositórios para `npx skills add` (default + env SKILLS_ALLOWLIST)."""
    repos = set(_DEFAULT_SKILL_REPOS)
    repos.update(r.strip() for r in os.getenv("SKILLS_ALLOWLIST", "").split(",") if r.strip())
    return repos


@tool
def install_external_skill(repo: str, skill: str) -> str:
    """Instala uma skill externa via `npx skills add <repo> --skill <skill>` (RESTRITO).

    Só aceita repositórios de uma allowlist (por padrão: vercel-labs/skills). Requer Node/npx
    e acesso de rede. A skill é instalada no diretório de skills e carregada em runtime.
    Se o repositório não estiver na allowlist, a instalação é recusada.
    """
    allowed = _allowed_skill_repos()
    if repo not in allowed:
        return (
            f"Repositório não permitido: {repo}\n"
            f"Allowlist atual: {sorted(allowed)}\n"
            "Um humano pode liberar via env SKILLS_ALLOWLIST."
        )
    if not re.fullmatch(r"[a-zA-Z0-9._-]+", skill):
        return "Nome de skill inválido. Use apenas letras, números, '.', '_' e '-'."
    if shutil.which("npx") is None:
        return "npx não está disponível no ambiente (Node não instalado na imagem)."

    SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    # A CLI `skills add` é interativa por padrão (seletor de agentes). As flags
    # `--agent "*" --yes --copy` a tornam não-interativa. Ela instala em
    # `<cwd>/.<agente>/skills/<skill>/SKILL.md` para vários agentes conhecidos;
    # rodamos num diretório temporário e extraímos uma cópia para SKILLS_DIR no
    # formato que o deepagents espera: `backend/skills/<skill>/SKILL.md`.
    with tempfile.TemporaryDirectory() as tmp:
        try:
            proc = subprocess.run(
                ["npx", "-y", "skills", "add", repo,
                 "--skill", skill, "--agent", "*", "--yes", "--copy"],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            return "Timeout (300s) ao instalar a skill."
        except OSError as exc:
            return f"Falha ao executar npx: {exc}"

        output = ((proc.stdout or "") + (proc.stderr or "")).strip()

        # os.walk percorre também os diretórios ocultos (.<agente>/skills/<skill>),
        # onde a CLI instala. Preferimos a pasta cujo nome é exatamente <skill>.
        src_dir = None
        fallback = None
        for root, _dirs, files in os.walk(tmp):
            if "SKILL.md" not in files or "node_modules" in root.split(os.sep):
                continue
            if os.path.basename(root) == skill:
                src_dir = root
                break
            fallback = fallback or root
        src_dir = src_dir or fallback
        if src_dir is None:
            return (
                f"[FALHOU] Skill '{skill}' não encontrada após a instalação "
                f"(exit {proc.returncode}).\n{output[-1500:]}"
            )

        dest_dir = SKILLS_DIR / skill
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        shutil.copytree(src_dir, dest_dir)

    return (
        f"[OK] Skill '{skill}' instalada em backend/skills/{skill}/ (de {repo}). "
        "Ficará disponível para o assistant nas próximas interações."
    )
