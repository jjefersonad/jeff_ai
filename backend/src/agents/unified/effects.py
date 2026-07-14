"""Registry de efeitos para o `EnvelopeMiddleware` da change `unified-agent-realignment`.

Corresponde à **Decision D3** do design e à task `envelope-2`. O envelope
raciocina sobre **efeito**, não sobre nome de tool, para fechar o cenário
`task-scoped-permissions` REQ-005 ("contorno por tool equivalente"): se
`edit_file` está fora do envelope, o modelo não consegue o mesmo efeito
via `write_file` sobre um arquivo existente. Um envelope que lista nomes
é contornável por sinônimo; um que lista **capacidades** não é.

## Capacidades

A enum `Capability` lista os efeitos possíveis. Cada tool é mapeada para
**uma ou mais** capacidades — `install_external_skill` é simultaneamente
`network` (download via `npx`) e `write_new` (escreve em `backend/skills/`).

| Capability       | Significado                                                              |
|------------------|--------------------------------------------------------------------------|
| `read`           | Lê estado do repositório ou do agente.                                   |
| `write_new`      | Cria um arquivo / diretório que NÃO existia.                            |
| `write_existing` | Modifica um arquivo que JÁ existia.                                      |
| `vcs`            | Lê ou modifica o estado do git (commits, branches, diffs).               |
| `shell`          | Executa um comando arbitrário no shell. **Curinga** (D4).                |
| `network`        | Faz requisição para fora (HTTP, npm, arXiv, ...).                        |
| `unknown`        | Tool que não está no registry. Default seguro para tools MCP de terceiro.|

## Por que `unknown` é o default (Q3 do design)

Decidido pelo usuário em 2026-07-12: **registry manual, `unknown` default**
para a v1. Ferramentas de servidores MCP de terceiros, ou geradas em runtime
via `save_generated_tool`, simplesmente não estão no dicionário em tempo
de build. Classificá-las heuristicamente sobre a descrição (string) seria
escalável mas falível, e qualquer falso positivo vira buraco de segurança.
A combinação `unknown` + `tiered-approval` REQ-002 (Tier 3+ fail-safe)
fecha o caso por construção.

## Curinga: `shell` (D4)

`shell` engloba, na prática, todos os outros efeitos: `sed -i` é
`write_existing`, `git commit` é `vcs`, `curl` é `network`. Por isso:

- O envelope é **uma camada restritiva** sobre o `TIER_REGISTRY` —
  nunca alarga, só estreita.
- Se um envelope conceder `shell` E simultaneamente negar `write_existing`
  ou `vcs`, há **contradição detectável** (`is_contradictory_envelope`).
  O sistema SHALL reportar essa contradição ao usuário em vez de mentir
  que está contido.

## Classificação dinâmica: `write_file`

A maioria das tools tem efeito estático (uma tool = uma capability).
A exceção é `write_file` (do `FilesystemMiddleware` do deepagents):
ela escreve em um path que **pode ou não existir**. Se o path já existe,
o efeito é `write_existing` — mesmo efeito de `edit_file`, e portanto
sujeito ao mesmo gate. Se o path é novo, é `write_new`.

Para isso, `classify()` aceita o `tool_call` (dict com `name` e `args`)
e usa um classificador dinâmico quando a tool é path-dependente.

## Auditoria

O registry é um dicionário plano em código. Para auditar, basta ler
este arquivo. Toda tool nova deve ser adicionada **explicitamente** —
o teste `test_every_agent_tool_has_an_effect_entry` impede que se
esqueça disso.
"""
from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any, Callable, Final


class Capability(str, Enum):
    """Os efeitos possíveis que uma tool pode ter.

    `str` mixin para serialização trivial (JSON, logging).
    """

    READ = "read"
    WRITE_NEW = "write_new"
    WRITE_EXISTING = "write_existing"
    VCS = "vcs"
    SHELL = "shell"
    NETWORK = "network"
    UNKNOWN = "unknown"


# Aliases semânticos para uso externo.
CAPABILITY_NAMES: Final[tuple[str, ...]] = tuple(c.value for c in Capability)


# --------------------------------------------------------------------------- #
# Piso (floor): o que roda SEM concessão humana.
# --------------------------------------------------------------------------- #
# `task-scoped-permissions` REQ-001: "tarefa que usa só Tier 1 (leitura/pesquisa)
# NÃO pede envelope — sem atrito onde não há risco". Sem um piso, o envelope
# default (deny-all) esconderia até o `read_file`, e uma tarefa de leitura pura
# ficaria sem nenhuma tool. O piso é o que torna o deny-all utilizável.
#
# `NETWORK` está no piso porque `internet_search` e `search_arxiv` são Tier 1 —
# "pesquisa" é literalmente o caso que o REQ-001 nomeia como sem-atrito.
# `WRITE_NEW` está no piso porque Tier 2 (criar arquivo NOVO, gerar .docx,
# `save_memory`) já executa direto pela política de tier; o envelope não
# alarga nada ao incluí-lo (REQ-006).
#
# O que está FORA do piso é o que carrega risco irreversível: modificar um
# arquivo que já existia, mexer no git, rodar shell, ou uma tool que nunca
# vimos (MCP de terceiro).
FLOOR_CAPABILITIES: Final[frozenset[Capability]] = frozenset(
    {Capability.READ, Capability.WRITE_NEW, Capability.NETWORK}
)


# --------------------------------------------------------------------------- #
# Plano de controle: tools que o envelope NUNCA gateia.
# --------------------------------------------------------------------------- #
# Estas tools não tocam o repositório, o git, o shell nem a rede — elas operam
# o próprio agente. Gateá-las quebraria o agente sem ganho de segurança:
#
# - `propose_envelope`: a tool com que o agente PEDE o envelope. Escondê-la
#   tornaria a concessão impossível — o agente nunca conseguiria propor.
# - `write_todos`: planejamento. Escreve na lista de tarefas em memória (state
#   do grafo), não no disco.
# - `task`: despacha um subagente.
#
# ⚠️ LACUNA CONHECIDA (`task`): o subagente roda em um grafo próprio, e NÃO está
# provado que ele herda o `EnvelopeMiddleware` do pai. Enquanto isso não for
# verificado, as tool calls DENTRO de um subagente podem não passar pelo
# envelope. Isso é enforcement através da fronteira de subagente — escopo das
# tasks `envelope-5`/`envelope-6`, não desta. Registrado aqui para não virar
# uma suposição silenciosa.
CONTROL_PLANE_TOOLS: Final[frozenset[str]] = frozenset(
    {"propose_envelope", "write_todos", "task"}
)


# --------------------------------------------------------------------------- #
# Wildcard (D4): o que `shell` engloba na prática.
# --------------------------------------------------------------------------- #
# Conceder `shell` na prática concede: edição de arquivos (`sed -i`),
# operações de git (`git commit`), e rede (`curl`). O sistema DEVE detectar
# a contradição entre um envelope que concede `shell` e nega essas
# capacidades.
SHELL_ENCOMPASSES: Final[frozenset[Capability]] = frozenset(
    {Capability.WRITE_EXISTING, Capability.VCS, Capability.NETWORK}
)


def is_contradictory_envelope(granted: set[Capability]) -> bool:
    """Verifica contradição D4: `shell` no envelope + nega um efeito que ele engloba.

    **D4 do design:** um envelope que diz "pode shell, não pode editar"
    mente. Esta função detecta isso. Note: a negação não está no
    parâmetro `granted` (que é só o conjunto POSITIVO) — quem chama
    precisa checar contra a intersecção com o conjunto de capabilities
    POSSÍVEIS. Para a v1, basta checar se `shell` está em `granted`
    e o envelope também explicitamente diz que **não** quer
    `write_existing`, `vcs` ou `network` — o que o chamador conhece
    via o envelope ESTRUTURADO, não o `granted`.
    """
    return Capability.SHELL in granted and bool(granted & SHELL_ENCOMPASSES)


# --------------------------------------------------------------------------- #
# Classificador dinâmico (path-aware).
# --------------------------------------------------------------------------- #
# Algumas tools têm efeito que depende dos argumentos em runtime — a
# exceção canônica é `write_file` (do `FilesystemMiddleware` do
# deepagents), que escreve em path novo ou existente. Para essas, a
# entrada do registry aponta para uma função em vez de uma tuple de
# capabilities. A função recebe o `tool_call` (dict) e devolve a
# capability efetiva.
#
# Para a v1, este classificador é SIMPLES: confia em uma anotação de
# `args["path"]` e pergunta ao filesystem se o path existe. Em ambiente
# sem filesystem (e.g. tool_call_id sem path), cai de volta para o
# ESTÁTICO do registry (que nesse caso é `write_new` — o caso comum).
DynamicClassifier = Callable[[dict[str, Any]], Capability]


def _classify_write_file(tool_call: dict[str, Any]) -> Capability:
    """Path-aware: `write_file` sobre path existente = `write_existing`.

    Args:
        tool_call: `{"name": "write_file", "args": {"path": "..."}}`

    Returns:
        `WRITE_EXISTING` se o path já existe no disco (dentro do repo
        real); `WRITE_NEW` caso contrário — incluindo o caso de
        path inválido, path fora do repo, ou erro de I/O, que
        trataríamos conservadoramente como "novo" (Tier 2 = notificação
        não-bloqueante, não silencioso).
    """
    args = tool_call.get("args", {})
    path = args.get("path") if isinstance(args, Mapping) else None
    if not isinstance(path, str) or not path:
        return Capability.WRITE_NEW
    # Verifica se o path existe no CWD (o `FilesystemMiddleware` resolve
    # relativo à raiz do backend). Import lazy para não acoplar este
    # módulo ao filesystem no import.
    try:
        import os

        return (
            Capability.WRITE_EXISTING
            if os.path.exists(path)
            else Capability.WRITE_NEW
        )
    except OSError:
        return Capability.WRITE_NEW


# --------------------------------------------------------------------------- #
# Registry: tool_name → capability(ies) OU classificador dinâmico.
# --------------------------------------------------------------------------- #
# Uma tool pode ter múltiplas capabilities (e.g. `install_external_skill`
# é `network + write_new`). Para tools estáticas, o valor é uma tuple
# imutável. Para tools dinâmicas, é uma tupla cujo ÚNICO elemento é um
# callable. A função `classify` lida com ambos.
#
# IMPORTANTE: para ferramentas de terceiros (MCP) que não estão aqui, o
# `classify()` devolve `UNKNOWN`. Isso é o que torna o envelope seguro
# por construção (REQ-008 do `task-scoped-permissions`).


def _read_only() -> tuple[Capability, ...]:
    return (Capability.READ,)


def _write_new() -> tuple[Capability, ...]:
    return (Capability.WRITE_NEW,)


def _write_existing() -> tuple[Capability, ...]:
    return (Capability.WRITE_EXISTING,)


def _vcs() -> tuple[Capability, ...]:
    return (Capability.VCS,)


def _shell() -> tuple[Capability, ...]:
    return (Capability.SHELL,)


def _network() -> tuple[Capability, ...]:
    return (Capability.NETWORK,)


def _network_write_new_shell() -> tuple[Capability, ...]:
    """`install_external_skill`: rede + escreve skill nova + **roda shell**.

    O `SHELL` não estava aqui e era um buraco: a tool é Tier 3, mas suas
    capacidades (`network`, `write_new`) estão ambas no `FLOOR_CAPABILITIES`.
    Pela regra do envelope (`_tool_allowed_in_envelope`), ela passaria **sem
    concessão nenhuma** — um `npx skills add` de repositório de terceiro
    rodando sem envelope.

    O `SHELL` é a classificação honesta: `install_external_skill` executa
    `npx skills add <repo>`, que é um comando de shell rodando código npm
    que o usuário não escreveu. Com `SHELL` (fora do piso), a tool passa a
    exigir concessão explícita.

    O invariante `test_tier_3_plus_tools_have_a_non_floor_capability` impede
    que essa classe de bug volte: toda tool de Tier 3+ DEVE ter ao menos uma
    capacidade fora do piso.
    """
    return (Capability.NETWORK, Capability.WRITE_NEW, Capability.SHELL)


def _dynamic_write_file() -> tuple[Capability | DynamicClassifier, ...]:
    """Entry para `write_file`: classificador dinâmico com fallback estático.

    A `WRITE_NEW` ao lado do callable serve dois propósitos:

    1. `_is_dynamic_entry` reconhece que há um callable.
    2. Quando `classify` é chamado SEM `tool_call` (e.g. na fase de
       proposta do envelope, em que a tool ainda não foi chamada),
       `_static_fallback_for_dynamic_entry` devolve `(WRITE_NEW,)` —
       o caso otimista comum. A confirmação da classificação real
       (`WRITE_EXISTING` se o path existir) só acontece em runtime,
       na hora da tool call.
    """
    return (Capability.WRITE_NEW, _classify_write_file)


# Cada chave é o `name` da tool (o mesmo usado no `interrupt_on` e
# registrado em `_UNIFIED_TOOLS`).
TOOL_EFFECTS: Final[Mapping[str, tuple[Any, ...]]] = {
    # --- Leitura ---------------------------------------------------------
    "read_file": _read_only(),
    "read_project_file": _read_only(),
    "ls": _read_only(),
    "list_project_files": _read_only(),
    "grep_project": _read_only(),
    # Built-ins do `FilesystemMiddleware` do deepagents. Não estavam no
    # registry: caíam em `UNKNOWN` e o envelope os ESCONDIA do modelo —
    # o agente perdia a busca por arquivo. São leituras puras.
    "glob": _read_only(),
    "grep": _read_only(),
    "search_memory": _read_only(),
    "list_memories": _read_only(),
    "get_sdd_state": _read_only(),
    "get_next_feature_number": _read_only(),
    "load_template": _read_only(),
    "validate_artifact": _read_only(),
    "find_external_skills": _read_only(),
    "list_skills_in_repo": _read_only(),
    "list_generated_tools": _read_only(),
    "get_date_time_current": _read_only(),
    "git_status": _read_only(),
    "git_diff": _read_only(),
    "git_branch": _read_only(),
    "fetch_reference_image": _read_only(),
    "check_reference_image": _read_only(),
    # `propose_envelope` é plano de controle (`CONTROL_PLANE_TOOLS`) — o
    # `is_control_plane` check em `_tool_allowed_in_envelope` intercepta
    # ANTES de `classify()` ser consultado, então este valor nunca decide
    # se a tool passa. A entrada existe só para satisfazer o audit de
    # `test_every_agent_tool_has_an_effect_entry` (toda tool do agente
    # precisa de uma entrada explícita) — `READ` por ser a mais inócua.
    "propose_envelope": _read_only(),
    # --- Escrita de NOVOS arquivos (Tier 2) ------------------------------
    "create_docx_document": _write_new(),
    "create_xlsx_spreadsheet": _write_new(),
    "create_pptx_presentation": _write_new(),
    "save_memory": _write_new(),
    "log_episode": _write_new(),
    "merge_generated_files": _write_new(),
    "create_feature_directory": _write_new(),
    "save_generated_tool": _write_new(),
    # `write_file` é o caso dinâmico: path novo = write_new, path
    # existente = write_existing.
    "write_file": _dynamic_write_file(),
    # --- Edição de EXISTENTES (Tier 3) -----------------------------------
    "edit_file": _write_existing(),
    "patch_file": _write_existing(),
    "multi_file_edit": _write_existing(),
    # Remove uma entrada EXISTENTE da memória — mesma categoria de `edit_file`
    # (modifica/destrói dado que já existia), ver `tier_config.py`.
    "delete_memory": _write_existing(),
    # --- VCS (Tier 3) ----------------------------------------------------
    "git_commit": _vcs(),
    "git_apply_commit": _vcs(),
    # --- Shell (Tier 4) — curinga D4 -------------------------------------
    "run_shell_command": _shell(),
    # --- Network ---------------------------------------------------------
    "internet_search": _network(),
    "search_arxiv": _network(),
    # `install_external_skill`: baixa de um repositório remoto, escreve em
    # `backend/skills/` E roda `npx` (shell). Ver `_network_write_new_shell`.
    "install_external_skill": _network_write_new_shell(),
    # --- Execução de testes (Tier 1) -------------------------------------
    "run_tests": _read_only(),
}


# --------------------------------------------------------------------------- #
# Classify
# --------------------------------------------------------------------------- #
def _expand_entry(entry: tuple[Any, ...]) -> tuple[Capability, ...]:
    """Normaliza uma entrada do registry para `tuple[Capability, ...]`.

    Entradas dinâmicas (que contêm um callable) precisam do `tool_call`
    para resolver; aqui só tratamos entradas ESTÁTICAS. O classificador
    dinâmico é tratado em `classify` diretamente.
    """
    if not entry:
        return (Capability.UNKNOWN,)
    out: list[Capability] = []
    for item in entry:
        if isinstance(item, Capability):
            out.append(item)
        # Itens callable ficam para `classify` resolver. Quando o
        # classificador é invocado sem `tool_call` (caso fallback),
        # substituímos o callable por `UNKNOWN` para indicar que não
        # conseguimos classificar estaticamente — é o mais conservador.
    return tuple(out) or (Capability.UNKNOWN,)


def _is_dynamic_entry(entry: tuple[Any, ...]) -> bool:
    """Verdadeiro se a entrada contém um classificador dinâmico."""
    return any(callable(item) for item in entry)


def _static_fallback_for_dynamic_entry(
    entry: tuple[Any, ...],
) -> tuple[Capability, ...]:
    """Fallback estático para entradas dinâmicas quando não há `tool_call`.

    Para `write_file` (e.g.), o fallback é `WRITE_NEW` — assume que o
    path é novo (caso comum em tarefas de scaffolding). Isto é
    deliberadamente otimista: se o classificador for chamado SEM args,
    preferimos deixar a tool passar (Tier 2 = notificação) do que
    marcar como `UNKNOWN` (Tier 3+ = interrupt). A regra "negar por
    padrão" continua valendo para tools TOTALMENTE ausentes do
    registry — apenas para dinâmicas SEM args usamos o fallback
    estático.

    O fallback é derivado da entrada do registry: pegamos a primeira
    capability estática (Capability, não callable). Se não houver
    nenhuma, devolvemos `UNKNOWN` (caso degenerado, mas explícito).
    """
    static_caps = [item for item in entry if isinstance(item, Capability)]
    if static_caps:
        return tuple(static_caps)
    return (Capability.UNKNOWN,)


def _mcp_manual_override(tool_name: str) -> Capability | None:
    """Consulta a classificação manual (task `mcp-3`) para uma tool MCP.

    Só tools qualificadas (`mcp__servidor__tool`, ver
    `mcp_tools_middleware._qualify_tool_names`) podem ter override — é a
    própria função de override (`mcp_tool_overrides.set_override`) quem
    valida isso na escrita. Aqui só lemos.

    Import lazy para não acoplar o carregamento deste módulo (importado
    cedo, em `tier_config`/`envelope_middleware`) à leitura de arquivo do
    override store. Arquivo ausente ou tool não classificada → `None`,
    e `classify` cai no fallback `UNKNOWN` de sempre.
    """
    if not tool_name.startswith("mcp__"):
        return None
    from src.agents.unified.mcp_tool_overrides import get_override

    raw = get_override(tool_name)
    if raw is None:
        return None
    try:
        return Capability(raw)
    except ValueError:
        # Override corrompido/valor inválido gravado fora da API oficial.
        # Cai no fail-safe em vez de propagar um erro de classificação.
        return None


def classify(
    tool_name: str,
    tool_call: dict[str, Any] | None = None,
) -> tuple[Capability, ...]:
    """Devolve as capabilities de `tool_name`.

    Args:
        tool_name: nome da tool (igual ao `name` registrado).
        tool_call: dict opcional `{"name": ..., "args": ...}`. Necessário
            para tools com classificador dinâmico (`write_file`). Se
            ausente e a tool for dinâmica, devolve o **fallback estático**
            do registry (capabilities explícitas ao lado do callable;
            ver `_static_fallback_for_dynamic_entry`).

    Returns:
        Tupla de capabilities. Tools MCP com classificação manual (task
        `mcp-3`) recebem a capability escolhida pelo humano. Tools
        desconhecidas sem override (MCP de terceiro não classificado, ou
        geradas em runtime) recebem `(UNKNOWN,)`. Tupla vazia é
        impossível — sempre há pelo menos um elemento.
    """
    entry = TOOL_EFFECTS.get(tool_name)
    if entry is None:
        override = _mcp_manual_override(tool_name)
        if override is not None:
            return (override,)
        return (Capability.UNKNOWN,)

    if not _is_dynamic_entry(entry):
        return _expand_entry(entry)

    # Entrada dinâmica, mas fomos chamados SEM `tool_call`. Devolvemos
    # o fallback estático da entrada do registry (não `UNKNOWN`).
    if tool_call is None:
        return _static_fallback_for_dynamic_entry(entry)

    # Entrada dinâmica COM `tool_call`: invoca os classificadores.
    out: list[Capability] = []
    for item in entry:
        if isinstance(item, Capability):
            out.append(item)
        elif callable(item):
            try:
                result = item(tool_call)
            except Exception:
                # Em caso de erro do classificador, NÃO bloqueamos por
                # falha nossa — caímos em UNKNOWN (Tier 3+ fail-safe).
                result = Capability.UNKNOWN
            out.append(result)
        else:
            out.append(Capability.UNKNOWN)
    # Deduplica preservando ordem. Útil para `write_file` em que o
    # fallback `WRITE_NEW` e o resultado dinâmico coincidem.
    seen: set[Capability] = set()
    deduped: list[Capability] = []
    for c in out:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    return tuple(deduped) or (Capability.UNKNOWN,)


# --------------------------------------------------------------------------- #
# Helpers de envelope
# --------------------------------------------------------------------------- #
def has_capability(
    tool_name: str,
    capability: Capability,
    tool_call: dict[str, Any] | None = None,
) -> bool:
    """Atalho: a tool `tool_name` tem a capability `capability`?"""
    return capability in classify(tool_name, tool_call)


def is_unknown(tool_name: str) -> bool:
    """Verdadeiro se a tool não está no registry (`UNKNOWN`)."""
    return tool_name not in TOOL_EFFECTS


def is_control_plane(tool_name: str) -> bool:
    """Verdadeiro se a tool opera o AGENTE, não o mundo (ver `CONTROL_PLANE_TOOLS`)."""
    return tool_name in CONTROL_PLANE_TOOLS


def needs_grant(
    tool_name: str,
    tool_call: dict[str, Any] | None = None,
) -> bool:
    """Decide se a tool exige concessão humana ou roda no piso (sem atrito).

    Uma tool roda **sem envelope** apenas se TODAS as suas capacidades
    efetivas estiverem no `FLOOR_CAPABILITIES` — leitura, pesquisa, e
    criação de arquivo novo. Qualquer outra coisa (editar um arquivo que já
    existia, git, shell, ou uma tool desconhecida) exige concessão.

    A classificação é **path-aware**: `write_file` sobre um path que já
    existe tem efeito `write_existing` e portanto EXIGE concessão, mesmo
    sendo Tier 2 no `TIER_REGISTRY`. É isto que fecha o cenário
    "contorno por tool equivalente" do REQ-005 — o agente não escapa de
    `edit_file` bloqueado usando `write_file` no mesmo arquivo.
    """
    if is_control_plane(tool_name):
        return False
    effective = set(classify(tool_name, tool_call))
    return not effective <= FLOOR_CAPABILITIES


__all__ = [
    "CAPABILITY_NAMES",
    "CONTROL_PLANE_TOOLS",
    "FLOOR_CAPABILITIES",
    "Capability",
    "SHELL_ENCOMPASSES",
    "TOOL_EFFECTS",
    "classify",
    "has_capability",
    "is_contradictory_envelope",
    "is_control_plane",
    "is_unknown",
    "needs_grant",
]
