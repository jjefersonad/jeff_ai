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
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from langchain_core.tools import BaseTool, tool

# Logger de auditoria de comandos de shell (REQ-005). Cai nos logs do backend
# (docker logs / LangSmith). Cada execução aprovada registra command/cwd/exit.
_audit_log = logging.getLogger("jeff_ai.shell_audit")

_THIS = Path(__file__).resolve()
BACKEND_DIR = _THIS.parents[2]
REPO_ROOT = _THIS.parents[3]
GENERATED_DIR = BACKEND_DIR / "src" / "tools" / "generated"
APPROVED_MANIFEST = GENERATED_DIR / "approved.json"
SKILLS_DIR = BACKEND_DIR / "skills"

# Repositórios permitidos para instalação de skills externas (`npx skills add`).
# Pode ser estendida via env SKILLS_ALLOWLIST (lista separada por vírgula).
# Inclui os repos oficiais/confiáveis onde vivem as skills mais usadas (design,
# frontend, etc.). A DESCOBERTA (`find_external_skills`) NÃO é restrita — só a
# INSTALAÇÃO é limitada por esta allowlist.
_DEFAULT_SKILL_REPOS = {
    "vercel-labs/skills",
    "https://github.com/vercel-labs/skills",
    "vercel-labs/agent-skills",
    "https://github.com/vercel-labs/agent-skills",
    "anthropics/skills",
    "https://github.com/anthropics/skills",
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


# --------------------------------------------------------------------------- #
# 4. Descoberta de skills externas (busca REAL na CLI, não na web)
# --------------------------------------------------------------------------- #
# Remove códigos de escape ANSI (cores/spinners) da saída da CLI `skills`.
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
# `find`: linhas no formato "owner/repo@skill  <N> installs".
_FIND_RE = re.compile(r"^([\w.-]+/[\w.-]+@[\w.-]+)\s+([\d.]+[KM]?)\s+installs\b")


def _run_skills_cli(args: list[str], timeout: int = 120) -> tuple[bool, str]:
    """Roda `npx -y skills <args>` de forma NÃO-INTERATIVA e retorna (ok, saída limpa).

    stdout/stderr são capturados (logo, não há TTY → a CLI imprime resultados em vez
    de abrir o seletor interativo). Retorna `ok=False` com mensagem amigável se o
    `npx` não existir ou a execução falhar.
    """
    if shutil.which("npx") is None:
        return False, "npx não está disponível no ambiente (Node não instalado na imagem)."
    try:
        proc = subprocess.run(
            ["npx", "-y", "skills", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"Timeout ({timeout}s) ao executar `skills {' '.join(args)}`."
    except OSError as exc:
        return False, f"Falha ao executar npx: {exc}"
    clean = _ANSI_RE.sub("", (proc.stdout or "") + (proc.stderr or ""))
    return True, clean


@tool
def find_external_skills(query: str, owner: str = "") -> str:
    """Busca skills externas REAIS pela CLI `skills find` (NÃO use web/internet_search).

    Retorna skills existentes no ecossistema (nome no formato `owner/repo@skill` e
    número de instalações), rankeadas por popularidade. Use isto para descobrir o
    NOME e o REPO corretos ANTES de instalar — evita inventar nomes que não existem.
    `owner` (opcional) restringe a um dono do GitHub (ex.: 'anthropics').

    Depois de escolher, instale com `install_external_skill(repo=owner/repo, skill=skill)`
    — lembrando que a instalação só aceita repos da allowlist.
    """
    q = (query or "").strip()
    if not q:
        return "Informe um termo de busca (ex.: 'design', 'react testing')."
    args = ["find", q]
    if owner.strip():
        args += ["--owner", owner.strip()]
    ok, out = _run_skills_cli(args)
    if not ok:
        return out

    results: list[str] = []
    lines = out.splitlines()
    for i, line in enumerate(lines):
        m = _FIND_RE.match(line.strip())
        if not m:
            continue
        pkg, installs = m.group(1), m.group(2)
        url = ""
        if i + 1 < len(lines):
            nxt = lines[i + 1].strip().lstrip("└").strip()
            if nxt.startswith("http"):
                url = nxt
        results.append(f"- {pkg}  ({installs} installs)" + (f"\n  {url}" if url else ""))

    if not results:
        return f"Nenhuma skill encontrada para '{q}'.\n\nSaída bruta:\n{out[-1200:]}"
    header = (
        f"Skills encontradas para '{q}'"
        + (f" (owner={owner.strip()})" if owner.strip() else "")
        + " — nome no formato owner/repo@skill:\n"
    )
    return header + "\n".join(results[:20])


@tool
def list_skills_in_repo(repo: str) -> str:
    """Lista as skills REAIS de um repositório via `skills add <repo> --list` (sem instalar).

    Use para confirmar os nomes exatos das skills de um repo ANTES de instalar
    (ex.: `list_skills_in_repo('vercel-labs/agent-skills')`). Evita erros de
    "No matching skills found" por nome inventado.
    """
    r = (repo or "").strip()
    if not re.fullmatch(r"(https?://[\w./-]+|[\w.-]+/[\w.-]+)", r):
        return "Repo inválido. Use 'owner/repo' (ex.: 'anthropics/skills')."
    ok, out = _run_skills_cli(["add", r, "--list"])
    if not ok:
        return out

    # Após "Available Skills", os NOMES são slugs isolados (sem espaço); as linhas
    # seguintes são descrições (frases com espaços). Filtramos os slugs.
    names: list[str] = []
    seen_header = False
    for raw in out.splitlines():
        line = raw.lstrip("│").strip()
        if "Available Skills" in line or "Available skills" in line:
            seen_header = True
            continue
        if not seen_header or not line:
            continue
        token = line.lstrip("-").strip()
        if re.fullmatch(r"[a-z0-9][a-z0-9._-]+", token):
            names.append(token)

    if not names:
        return f"Não consegui listar skills de '{r}'.\n\nSaída bruta:\n{out[-1200:]}"
    body = "\n".join(f"- {n}" for n in names)
    return (
        f"Skills disponíveis em '{r}':\n{body}\n\n"
        f"Para instalar: install_external_skill(repo='{r}', skill='<nome-acima>')."
    )


# --------------------------------------------------------------------------- #
# 5. Execução de shell com GATE humano obrigatório (interrupt_on)
# --------------------------------------------------------------------------- #
_SHELL_TIMEOUT = int(os.getenv("SHELL_COMMAND_TIMEOUT", "180"))

# Denylist de padrões destrutivos (defesa em PROFUNDIDADE, best-effort). NÃO
# substitui a aprovação humana do `interrupt_on`: é uma segunda camada que impede
# a EXECUÇÃO de comandos obviamente perigosos mesmo que aprovados por engano.
# Extensível via env SHELL_DENYLIST (regexes separados por ';').
_DEFAULT_SHELL_DENYLIST = [
    r"\brm\s+-[a-z]*r[a-z]*f[a-z]*\s+(/|/\*|~|\$HOME)(\s|$|/)",  # rm -rf / (e variações)
    r"\brm\s+-[a-z]*f[a-z]*r[a-z]*\s+(/|/\*|~|\$HOME)(\s|$|/)",  # rm -fr /
    r"\bmkfs(\.\w+)?\b",                                         # formatar filesystem
    r"\bdd\b[^\n]*\bof=/dev/",                                   # dd of=/dev/...
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",                # fork bomb :(){ :|:& };:
    r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba)?sh\b",            # curl|sh / wget|sh
    r">\s*/dev/(sd[a-z]|nvme\d|vd[a-z])\b",                     # sobrescrever disco
]


def _shell_denylist() -> list[str]:
    """Padrões da denylist (default embutido + env SHELL_DENYLIST, separada por ';')."""
    pats = list(_DEFAULT_SHELL_DENYLIST)
    pats += [p.strip() for p in os.getenv("SHELL_DENYLIST", "").split(";") if p.strip()]
    return pats


def _denylisted(command: str) -> str | None:
    """Retorna o padrão casado se `command` for destrutivo, senão None."""
    for pat in _shell_denylist():
        try:
            if re.search(pat, command):
                return pat
        except re.error:
            continue
    return None


@tool
def run_shell_command(command: str, workdir: str = "") -> str:
    """Executa um comando de shell arbitrário. REQUER APROVAÇÃO HUMANA antes de rodar.

    NADA é executado sem o usuário aprovar: o framework PAUSA no gate `interrupt_on`
    e mostra os botões aprovar / editar / reprovar. Só depois de "approve" o comando roda.

    - `command`: o comando a executar (rodado via `bash -lc`).
    - `workdir`: diretório de trabalho (padrão: raiz do backend). Não é sandbox — o
      comando roda com as permissões do processo do servidor.

    Retorna o código de saída e a saída combinada (stdout+stderr), truncada se longa.
    Use com responsabilidade: prefira comandos idempotentes e evite ações destrutivas.
    """
    cmd = (command or "").strip()
    if not cmd:
        return "Comando vazio — nada a executar."

    # Defesa em profundidade: recusa a EXECUÇÃO de padrões destrutivos, mesmo que
    # o comando tenha sido aprovado no gate. Best-effort — não substitui o gate.
    hit = _denylisted(cmd)
    if hit is not None:
        return (
            "[RECUSADO pela denylist de segurança] O comando casa um padrão destrutivo "
            f"({hit!r}) e NÃO foi executado. Ajuste o comando se a intenção for legítima.\n"
            "Nota: a denylist é best-effort e é uma 2ª camada — não substitui a aprovação humana."
        )

    cwd = str(BACKEND_DIR)
    if workdir.strip():
        target = Path(workdir).expanduser()
        if not target.is_dir():
            return f"workdir inválido (não é um diretório): {workdir}"
        cwd = str(target)

    try:
        proc = subprocess.run(
            ["bash", "-lc", cmd],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_SHELL_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return f"Timeout ({_SHELL_TIMEOUT}s) ao executar o comando."
    except OSError as exc:
        return f"Falha ao executar o comando: {exc}"

    # Auditoria (REQ-005): registra toda execução aprovada — sucesso E falha.
    # Não é alcançado para comandos vazios, denylisted ou rejeitados no gate.
    # Dados no próprio texto para garantir visibilidade nos logs (independe do formatter).
    _audit_log.info(
        "shell_audit command=%r cwd=%r exit=%s", cmd, cwd, proc.returncode
    )

    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if len(out) > _MAX_READ_CHARS:
        out = out[:_MAX_READ_CHARS] + "\n\n[...truncado...]"
    header = f"$ {cmd}\n(cwd={cwd}, exit={proc.returncode})"
    return f"{header}\n{out}" if out else f"{header}\n(sem saída)"
