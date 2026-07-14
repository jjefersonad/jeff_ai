"""Configuração declarativa de tiers de aprovação para o agente unificado.

O modelo de tier (4 níveis) substitui o antigo `interrupt_on` all-or-nothing
por uma matriz de risco que casa (ou supera) a UX do Claude Code:

- **Tier 1 — Auto**: leituras, buscas, execuções de teste, listagens.
  Executam imediatamente, sem `interrupt_on`.
- **Tier 2 — Prompted**: criação de arquivos NOVOS, geração de documentos
  Office, salvamento de memória, merge de artefatos. Executam
  imediatamente; o frontend exibe uma notificação não-bloqueante.
- **Tier 3 — Interrupt**: edições em arquivos EXISTENTES, commits git.
  Pausam via `interrupt_on` com preview de diff e botões
  `approve / edit / reject`.
- **Tier 4 — Block + Interrupt**: comandos de shell. Passam por um denylist de
  regexes (`self_extension._DEFAULT_SHELL_DENYLIST`, aplicado por
  `self_extension._denylisted()`, extensível via env `SHELL_DENYLIST`) ANTES do
  gate de aprovação e, se aprovados, executam via `run_shell_command`.

A função `build_interrupt_on(tool_names, registry)` converte este registry em um
dict `{tool_name: InterruptOnConfig}` no formato aceito por `create_deep_agent`.

**Deny-by-default**: entra no gate toda tool que não estiver explicitamente em
Tier 1 ou Tier 2 — inclusive as que o registry nunca viu (tools de servidores MCP
de terceiros, tools geradas em runtime). Ver o docstring de `build_interrupt_on`
para o porquê de a lista de tools reais ser necessária.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Mapping

from deepagents.middleware.subagents import InterruptOnConfig

# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
# Tier 1 — Auto-aprovado.
TIER_1_TOOLS: tuple[str, ...] = (
    # Leitura de arquivos (isolada e projeto).
    "read_file",
    "read_project_file",
    "ls",
    "list_project_files",
    # Leitura de documentos Office/PDF/HTML/CSV via markitdown.
    # Substitui a change `document-reading-tools` (que previa 4 readers
    # DDD). Ver `src/tools/read_document_tool.py` para rationale.
    "read_document",
    # Buscas e execuções de teste.
    "grep_project",
    "search_memory",
    "list_memories",
    "search_documents",
    "run_tests",
    # Git read-only + branch management.
    "git_status",
    "git_diff",
    "git_branch",
    # Utilitários.
    "get_date_time_current",
    # Buscas externas.
    "internet_search",
    "search_arxiv",
    # Imagens — leitura/referência.
    "fetch_reference_image",
    "check_reference_image",
    # SDD — leitura de estado/templates (não escrevem nada).
    "get_sdd_state",
    "get_next_feature_number",
    "load_template",
    "validate_artifact",
    # Self-extension — apenas LISTAGEM/BUSCA (não instalam nem escrevem nada).
    "find_external_skills",
    "list_skills_in_repo",
    "list_generated_tools",
    # Plano de controle do envelope de permissões (`effects.CONTROL_PLANE_TOOLS`,
    # task `envelope-7`). PRECISA ficar em Tier 1: `propose_envelope_tool` chama
    # `interrupt()` internamente — ESSE é o gate real da proposta. Se caísse no
    # default (Tier 3, `UNKNOWN_TOOL_TIER`), o `interrupt_on` genérico pausaria
    # ANTES da própria tool rodar, produzindo dois interrupts empilhados para uma
    # única decisão humana (aprovar a chamada da tool + depois conceder o
    # envelope) — exatamente o tipo de atrito redundante que o design pede para
    # evitar (risco R1, fadiga de aprovação).
    "propose_envelope",
)

# Tier 2 — Escrita de NOVOS arquivos (sem interrupt_on; notificação no front).
TIER_2_TOOLS: tuple[str, ...] = (
    "write_file",                # apenas quando o path não existe (gate no grafo)
    "create_docx_document",
    "create_xlsx_spreadsheet",
    "create_pptx_presentation",
    "save_memory",
    "log_episode",
    "ingest_document",
    "merge_generated_files",
    # Cria o scaffold de uma feature em outputs/.specify/ (arquivos NOVOS).
    "create_feature_directory",
    # Escreve um módulo Python em STAGING (src/tools/generated/). NÃO ativa nada:
    # exige que um humano revise, adicione o nome a `approved.json` e reinicie.
    # Esse gate fora-de-banda é o que a mantém em Tier 2 e não em Tier 3.
    "save_generated_tool",
)

# Tier 3 — Edição de EXISTENTES + commit (interrupt_on com diff preview).
TIER_3_TOOLS: tuple[str, ...] = (
    "edit_file",
    "patch_file",
    "multi_file_edit",
    "git_commit",
    # `git_apply_commit` é a tool que EFETIVAMENTE roda `git add` + `git commit`
    # (o `git_commit` só devolve um preview). Ela estava FORA do registry e caía
    # no default 2 — que executa direto, sem gate. Ou seja: o modelo podia pular
    # o `git_commit` e commitar sem nenhuma aprovação humana, tornando o gate de
    # Tier 3 do `git_commit` puro teatro. Demonstrado na task `floor-4`.
    "git_apply_commit",
    # Executa `npx skills add <repo>` e instala conteúdo de TERCEIRO em
    # backend/skills/, que o deepagents carrega AO VIVO (sem restart). Roda código
    # npm de terceiro. A `SKILLS_ALLOWLIST` limita QUAIS repos, mas não substitui
    # a aprovação humana de instalar. Estava sem gate até a task `floor-5`.
    "install_external_skill",
    # Remove uma entrada EXISTENTE da memória de longo prazo (`memory_tools.py`,
    # task `memory-2`). Mesma categoria de risco que `edit_file`/`patch_file`:
    # modifica/destrói dado que já existia, não cria dado novo — por isso Tier 3
    # e não Tier 2 (onde ficam `save_memory`/`log_episode`, que só criam).
    "delete_memory",
)

# Tier 4 — Shell com denylist (interrupt_on + gate de segurança prévio).
TIER_4_TOOLS: tuple[str, ...] = (
    "run_shell_command",
)


# Registry declarativo final: tool_name → tier (1..4).
TIER_REGISTRY: Mapping[str, int] = {
    **{name: 1 for name in TIER_1_TOOLS},
    **{name: 2 for name in TIER_2_TOOLS},
    **{name: 3 for name in TIER_3_TOOLS},
    **{name: 4 for name in TIER_4_TOOLS},
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
# Tier atribuído a uma tool que NÃO está no registry (ex.: tool vinda de um
# servidor MCP de terceiro, ou gerada em runtime via `save_generated_tool`).
# É 3 — ou seja, PEDE APROVAÇÃO. Não dá para classificar o risco de uma tool que
# nunca vimos, então o default tem que ser negar, não permitir.
UNKNOWN_TOOL_TIER: int = 3

# Decisões permitidas no interrupt. O `InterruptOnConfig` aceita exatamente estes
# literais — anotar como `str` fazia o mypy reclamar em `build_interrupt_on`.
Decision = Literal["approve", "edit", "reject", "respond"]
ALLOWED_DECISIONS: tuple[Decision, ...] = ("approve", "edit", "reject")


# Descrições curtas para o `interrupt_on`. Mostradas ao usuário no painel de
# aprovação (frontend). Devem ser 1-2 linhas e começar com verbo no imperativo.
# Quando a chave é um `int` (tier), aplica-se a todas as tools daquele tier
# que não tenham descrição específica. Quando a chave é um `str` (tool name),
# sobrescreve a descrição padrão daquele tier.
TIER_DESCRIPTIONS: Mapping[object, str] = {
    # Defaults por tier.
    3: "Aprovação humana antes de aplicar edições em arquivos existentes.",
    4: "Aprovação humana antes de executar comando de shell (passa denylist).",
    # Overrides por tool (Tier 3).
    "git_commit": "Aprovação humana antes de criar commit git (preview do diff).",
    "git_apply_commit": "Aprovação humana antes de EFETIVAR o commit git.",
    "install_external_skill": (
        "Aprovação humana antes de instalar uma skill de terceiro "
        "(roda `npx skills add` e o conteúdo é carregado ao vivo)."
    ),
    "delete_memory": "Aprovação humana antes de remover uma entrada da memória de longo prazo.",
    # Overrides por tool (Tier 4).
    "run_shell_command": "Aprovação humana antes de executar comando de shell (passa denylist).",
}


def get_tier(tool_name: str) -> int:
    """Devolve o tier de `tool_name`, ou `UNKNOWN_TOOL_TIER` (3) se desconhecida.

    Uma tool fora do registry PEDE APROVAÇÃO. Não é possível classificar o risco
    de algo que nunca vimos — e a partir do `mcp-client` o agente carrega tools de
    servidores de terceiros que, por construção, não podem estar no registry em
    tempo de build.

    (Antes o default era 2, e o docstring afirmava que isso era "conservador:
    nunca fica sem gate". Era falso: Tier 2 executa direto.)
    """
    return TIER_REGISTRY.get(tool_name, UNKNOWN_TOOL_TIER)


# --------------------------------------------------------------------------- #
# Diff preview (task `unified-dev-agent-task-frontend-2`)
# --------------------------------------------------------------------------- #
# O langchain `ActionRequest` (langchain/agents/middleware/human_in_the_loop.py)
# só tem `name` / `args` / `description` — não há campo `diff` no protocolo.
# Em vez de estender o schema (R6 do design: requer fork/monkey-patch no
# langchain), embutimos o diff formatado em markdown DENTRO de `description`,
# prefixado pelo `DIFF_MARKER` abaixo. O `ToolApprovalInterrupt` (frontend)
# detecta o marcador e renderiza `<DiffPreview>` em vez do `<pre>` cru.
#
# Por que callable e não string fixa: o `description` pode ser
# `str | Callable[[ToolCall, AgentState, Runtime], str]` (oficial do langchain).
# Callables recebem o `tool_call` real e podem inspecionar `args` (path, old,
# new, ...). É o ponto de extensão que o langchain já documenta para conteúdo
# dinâmico por chamada.
DIFF_MARKER: str = "<<<DIFF>>>"

# Limites de truncamento (R5). Acima disso, o diff é cortado com aviso.
_DIFF_MAX_LINES: int = 200
_DIFF_MAX_BYTES: int = 8 * 1024
_DIFF_MULTIFILE_MAX_FILES: int = 3


def _read_text_safely(path: str) -> str | None:
    """Lê `path` como UTF-8 (com `errors='replace'`). Retorna None se falhar.

    Não confia no path — se o path estiver fora do `REPO_ROOT` ou não existir,
    o frontend recebe `None` e cai no fallback (description estática, sem
    diff). O interrupt NUNCA trava por causa do diff.
    """
    try:
        p = Path(path)
        if not p.is_file():
            return None
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _truncate_diff(text: str) -> str:
    """Aplica cap de linhas e bytes. Acima do limite, anexa aviso."""
    lines = text.splitlines()
    if len(lines) > _DIFF_MAX_LINES:
        kept = lines[:_DIFF_MAX_LINES]
        omitted = len(lines) - _DIFF_MAX_LINES
        text = "\n".join(kept) + f"\n[…{omitted} linhas omitidas…]"
        lines = text.splitlines()
    if len(text.encode("utf-8")) > _DIFF_MAX_BYTES:
        # Truncamento por bytes aproximado: corta em 8KB e re-decodifica.
        cut = text.encode("utf-8")[:_DIFF_MAX_BYTES].decode("utf-8", "replace")
        text = cut + "\n[…truncado em 8KB…]"
    return text


def _diff_for_edit_file(args: Mapping[str, Any]) -> str | None:
    """`edit_file(path, old_string, new_string)` — diff `[-old / +new]`."""
    path = args.get("path")
    old = args.get("old_string")
    new = args.get("new_string")
    if not isinstance(path, str) or not isinstance(old, str) or not isinstance(new, str):
        return None
    # Lê o arquivo só para descobrir o line range do `old_string` (cosmético).
    # Se a leitura falhar, ainda devolvemos o diff sem line numbers.
    line_info = ""
    src = _read_text_safely(path)
    if src is not None and old in src:
        # 1-indexed line range.
        before = src.split(old)[0]
        start_line = before.count("\n") + 1
        old_lines = old.count("\n") + 1
        new_lines = new.count("\n") + 1
        end_line = start_line + max(old_lines, new_lines) - 1
        line_info = f" (linhas {start_line}-{end_line})"
    hunk = f"@@ -1,{old.count(chr(10)) + 1} +1,{new.count(chr(10)) + 1} @@\n"
    for ln in old.splitlines() or [""]:
        hunk += f"-{ln}\n"
    for ln in new.splitlines() or [""]:
        hunk += f"+{ln}\n"
    body = _truncate_diff(hunk)
    return f"{DIFF_MARKER}edit_file — `{path}`{line_info}\n\n```diff\n{body}```"


def _diff_for_patch_file(args: Mapping[str, Any]) -> str | None:
    """`patch_file(path, diff_text)` — diff unificado vem pronto nos args."""
    path = args.get("path")
    diff_text = args.get("diff_text")
    if not isinstance(path, str) or not isinstance(diff_text, str):
        return None
    body = _truncate_diff(diff_text)
    return f"{DIFF_MARKER}patch_file — `{path}`\n\n```diff\n{body}```"


def _diff_for_multi_file_edit(args: Mapping[str, Any]) -> str | None:
    """`multi_file_edit(edits=[{path, old, new}, ...])` — concatena hunks."""
    edits = args.get("edits")
    if not isinstance(edits, list):
        return None
    chunks: list[str] = []
    file_count = 0
    for e in edits:
        if not isinstance(e, Mapping):
            continue
        path = e.get("path")
        old = e.get("old_string") or e.get("old")
        new = e.get("new_string") or e.get("new")
        if not isinstance(path, str) or not isinstance(old, str) or not isinstance(new, str):
            continue
        file_count += 1
        if file_count > _DIFF_MULTIFILE_MAX_FILES:
            chunks.append(f"\n[…+{len(edits) - _DIFF_MULTIFILE_MAX_FILES} arquivos no diff completo…]\n")
            break
        hunk = (
            f"--- a/{path}\n"
            f"+++ b/{path}\n"
            f"@@ -1,{old.count(chr(10)) + 1} +1,{new.count(chr(10)) + 1} @@\n"
        )
        for ln in old.splitlines() or [""]:
            hunk += f"-{ln}\n"
        for ln in new.splitlines() or [""]:
            hunk += f"+{ln}\n"
        chunks.append(hunk)
    if not chunks:
        return None
    body = _truncate_diff("\n".join(chunks))
    return f"{DIFF_MARKER}multi_file_edit — {file_count} arquivo(s)\n\n```diff\n{body}```"


def _diff_for_git_commit(args: Mapping[str, Any]) -> str | None:
    """`git_commit(message, files=None)` — preview do diff pré-execução.

    O langchain HITL pausa ANTES da tool rodar, então o diff que vai ser
    commitado (depois de `auto_stage`) ainda não existe. O que mostramos é:
        - se `files` foi passado: `git diff -- <files>` (unstaged) + untracked;
        - senão: `git diff --staged`.

    R1 do design: o interrupt nunca trava. Se o git falhar, devolvemos a
    mensagem no body e seguimos.
    """
    message = args.get("message")
    files = args.get("files")
    if not isinstance(message, str):
        return None
    sections: list[str] = []
    try:
        if files:
            cmd = ["git", "diff", "--"] + list(files)
        else:
            cmd = ["git", "diff", "--staged"]
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=5
        )
        if result.stdout:
            sections.append(result.stdout)
    except (subprocess.SubprocessError, OSError):
        sections.append("(não foi possível ler `git diff`)")
    if not sections:
        sections.append(
            "(sem mudanças staged)"
            if not files
            else "(sem mudanças nos arquivos informados)"
        )
    body = _truncate_diff("\n".join(sections))
    safe_message = message.replace("`", "\\`")
    return f"{DIFF_MARKER}git_commit\n\nMensagem: `{safe_message}`\n\n```diff\n{body}```"


# Mapa tool_name → nome do helper de diff. Usar `globals().get(name)` no
# momento da chamada (em vez de armazenar a referência no dict) permite
# monkey-patching em testes e hot-reload em dev — o callable sempre
# resolve o símbolo mais recente do módulo.
_DIFF_HELPERS: Mapping[str, str] = {
    "edit_file": "_diff_for_edit_file",
    "patch_file": "_diff_for_patch_file",
    "multi_file_edit": "_diff_for_multi_file_edit",
    "git_commit": "_diff_for_git_commit",
}


def _interrupt_description_for(
    tool_call: Mapping[str, Any],
    _state: Any = None,
    _runtime: Any = None,
) -> str:
    """Callable para `InterruptOnConfig.description` (langchain HITL).

    Para tools com helper de diff registrado, prefixa o markdown com
    `DIFF_MARKER` e envolve num bloco ```diff. Para as demais, delega ao
    `_description_for` estático. Qualquer exceção (helper falhando) cai
    para a descrição estática — o interrupt nunca trava por causa do diff.
    """
    name = tool_call.get("name", "")
    args = tool_call.get("args") or {}
    tier = TIER_REGISTRY.get(name, UNKNOWN_TOOL_TIER)
    helper_name = _DIFF_HELPERS.get(name)
    if helper_name is not None and isinstance(args, Mapping):
        try:
            helper = globals().get(helper_name)
            if helper is not None:
                diff_md = helper(args)
                if diff_md is not None:
                    return diff_md
        except Exception:
            # Falha no diff é silenciosa — interrupt recebe a description estática.
            pass
    return _description_for(name, tier)


def _description_for(tool_name: str, tier: int) -> str:
    """Resolve a descrição do interrupt: override por tool > default por tier."""
    if tool_name in TIER_DESCRIPTIONS:
        return TIER_DESCRIPTIONS[tool_name]  # type: ignore[index]
    default = TIER_DESCRIPTIONS.get(tier)
    if default is not None:
        return default  # type: ignore[return-value]
    return f"Aprovação humana obrigatória (tier {tier})."


def build_interrupt_on(
    tool_names: Iterable[str] = (),
    registry: Mapping[str, int] = TIER_REGISTRY,
    *,
    min_tier: int = 3,
) -> dict[str, InterruptOnConfig]:
    """Constrói o dict `interrupt_on` aceito por `create_deep_agent`.

    **Deny-by-default.** Passe em `tool_names` os nomes das tools REALMENTE
    registradas no agente. Toda tool que não estiver explicitamente em Tier 1 ou
    Tier 2 entra no gate — inclusive as que o registry nunca viu.

    Por que a lista de tools é necessária
    -------------------------------------
    O `HumanInTheLoopMiddleware` do langchain gateia assim::

        if (config := self.interrupt_on.get(tool_call["name"])) is not None:

    Ou seja: **tool ausente do dict simplesmente executa.** Antes, esta função
    iterava só o `registry` — então uma tool fora dele nunca entrava no dict e
    nunca era gateada, por mais alto que fosse o tier "default" do `get_tier`.
    Não bastava mudar o default: era preciso conhecer as tools reais.

    Isso não é hipotético. Na task `floor-4` descobrimos que `git_apply_commit`
    (a tool que de fato roda `git add` + `git commit`) estava fora do registry e
    commitava SEM NENHUMA aprovação humana — tornando o gate de Tier 3 do
    `git_commit` puro teatro. Com deny-by-default, esse caso não teria existido.

    Parameters
    ----------
    tool_names:
        Nomes das tools registradas no agente. Se vazio, só o `registry` é
        considerado (comportamento legado — não use em produção).
    registry:
        Mapping `tool_name → tier`. Default: o `TIER_REGISTRY` global.
    min_tier:
        Tier mínimo para entrar no gate. Default 3 (Tier 3 e Tier 4).
    """
    out: dict[str, InterruptOnConfig] = {}
    for name in set(registry) | set(tool_names):
        tier = registry.get(name, UNKNOWN_TOOL_TIER)
        if tier < min_tier:
            continue
        # Tools com helper de diff ganham `description` callable — o langchain
        # invoca no momento do interrupt com o `tool_call` real (com `args`).
        # Demais tools continuam com a string estática pré-avaliada.
        if name in _DIFF_HELPERS:
            description: str | Callable[..., str] = _interrupt_description_for
        else:
            description = _description_for(name, tier)
        out[name] = InterruptOnConfig(
            allowed_decisions=list(ALLOWED_DECISIONS),
            description=description,
        )
    return out


__all__ = [
    "ALLOWED_DECISIONS",
    "DIFF_MARKER",
    "TIER_1_TOOLS",
    "TIER_2_TOOLS",
    "TIER_3_TOOLS",
    "TIER_4_TOOLS",
    "TIER_DESCRIPTIONS",
    "TIER_REGISTRY",
    "UNKNOWN_TOOL_TIER",
    "Decision",
    "build_interrupt_on",
    "get_tier",
]
