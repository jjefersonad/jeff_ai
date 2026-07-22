"""Grafo unificado Jeff AI — entrypoint único, um system prompt, uma pilha de tools.

`unified` é o único grafo real. `agent`, `sdd_agent` e `assistant`
(`src.composition.graphs`) são aliases que apontam para o mesmo grafo
compilado, mantidos por retrocompatibilidade com `assistantId` salvos no
frontend — não fixam comportamento algum (task `modes-2` decide o destino
final desses aliases).

## Não existe mais sistema de modos (task `modes-1)

Havia um sistema de 7 "modos" (`requirements`/`sdd`/`chat`/`code`/`test`/
`git`/`refactor`) com classificador por regex e um prompt por modo. Ele foi
**removido**, não corrigido: verificado no código, o classificador
(`classify_mode()`) tinha zero call sites, ninguém lia `configurable["mode"]`,
e todos os grafos sempre rodavam o mesmo prompt (`chat`) — a tabela de modos
nunca teve efeito algum em produção. Como todas as tools sempre estiveram
registradas para todos os "modos" (o roteamento nunca filtrava `_UNIFIED_TOOLS`),
remover o sistema não retira nenhuma capacidade: só para de fingir que uma
seleção acontecia.

Um `configurable.mode` enviado por um frontend antigo é ignorado silenciosamente
— nada no grafo lê essa chave.

## Data atual no contexto (change `current-date-context`)

A data atual é embutida na **primeira linha** do `_SYSTEM_PROMPT` no momento
do import do módulo, e todo turno subsequente do agente a vê sem precisar
chamar tool. Mudar `JEFF_AI_TZ` (env, IANA name) requer restart do processo
para pegar a mudança — drift de até 24h é aceitável em processos long-running;
para precisão de minutos/segundos, o agente usa `get_date_time_current`.
A função `_resolve_tz()` é reusada pela tool `internet_search` (ver
`src/tools/tavily_tool.py`).

## Subagentes

`_UNIFIED_SUBAGENTS` contém exatamente um subagente: `image_design_subagent`
(contexto isolado, gate `interrupt_on` próprio, memória de estilo por thread —
a única razão legítima para um subagente neste produto). SDD e requisitos são
entregues como skills (`backend/skills/{sdd,requirements}/SKILL.md`), não
subagentes — ver task `skills-4` e a spec `skill-based-capabilities`.

## Approval tiers

`interrupt_on` é computado dinamicamente a partir de
`src.agents/unified/tier_config.py` (Decision D4) — apenas tools de Tier 3+
entraram no gate de aprovação humana. O frontend exibe o diff preview via
`ToolApprovalInterrupt` (frontend fora do escopo deste módulo).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # noqa: F401  (re-export)

from deepagents import create_deep_agent
from dotenv import load_dotenv

from src.agents.subagents.image_design import image_design_subagent
from src.agents.unified.datetime_utils import (
    _resolve_tz,  # noqa: F401  (re-export p/ spec REQ-003)
)
from src.agents.unified.envelope_middleware import EnvelopeMiddleware
from src.agents.unified.envelope_proposal import (
    EnvelopeLifecycleMiddleware,
    propose_envelope_tool,
)
from src.agents.unified.mcp_tools_middleware import McpToolsMiddleware
from src.agents.unified.scoped_skills_middleware import ScopedSkillsMiddleware
from src.agents.unified.tier_config import build_interrupt_on
from src.composition.backends import FsRoute, make_backend_factory
from src.models.fallback_model import unified_model
from src.tools.code_editing_tools import (
    edit_file,
    grep_project,
    multi_file_edit,
    patch_file,
)
from src.tools.create_docx_document_tool import create_docx_document
from src.tools.create_pptx_presentation_tool import create_pptx_presentation
from src.tools.create_xlsx_spreadsheet_tool import create_xlsx_spreadsheet
from src.tools.deep_agent_tools import get_date_time_current
from src.tools.document_memory_tools import ingest_document, search_documents
from src.tools.fetch_reference_image_tool import (
    check_reference_image,
    fetch_reference_image,
)
from src.tools.git_tools import (
    git_apply_commit,
    git_branch,
    git_commit,
    git_diff,
    git_status,
)
from src.tools.memory_tools import (
    delete_memory,
    list_memories,
    log_episode,
    save_memory,
    search_memory,
)
from src.tools.read_document_tool import read_document
from src.tools.scientific_search_tool import search_arxiv
from src.tools.sdd_tools import (
    create_feature_directory,
    get_next_feature_number,
    get_sdd_state,
    load_template,
    validate_artifact,
)
from src.tools.self_extension import (
    find_external_skills,
    install_external_skill,
    list_generated_tools,
    list_project_files,
    list_skills_in_repo,
    load_approved_tools,
    read_project_file,
    run_shell_command,
    save_generated_tool,
)
from src.tools.tavily_tool import internet_search
from src.tools.technical_spec_tools import merge_generated_files
from src.tools.test_runner_tools import run_tests

load_dotenv()

_log = logging.getLogger(__name__)

# `_resolve_tz` foi movido para `src/agents/unified/datetime_utils.py` por causa
# de ciclo de import: `agent.py` importa `internet_search` (de `tavily_tool.py`),
# que precisava de `_resolve_tz`. O design original (D6) não previu o ciclo.
# A spec REQ-003 de `current-date-context` exige que `_resolve_tz` seja
# exportada de `agent.py` — esse requisito é satisfeito via re-export
# (`from ... import _resolve_tz` no topo deste módulo).

# --------------------------------------------------------------------------- #
# Paths (replicam o que cada grafo legado definia)
# --------------------------------------------------------------------------- #
PATH_DIR = Path(__file__).resolve().parents[3]  # .../jeff_ai/backend
REPO_ROOT = PATH_DIR.parent                     # .../jeff_ai
SKILLS_DIR = PATH_DIR / "skills"
WORKSPACE_DIR = PATH_DIR / "workspace"
OUTPUTS_DIR = PATH_DIR / "outputs"
SPECIFY_DIR = OUTPUTS_DIR / ".specify"
TEMPLATES_DIR = PATH_DIR / "templates" / "sdd"

# Garante diretórios de outputs no boot.
for d in (WORKSPACE_DIR, OUTPUTS_DIR, SPECIFY_DIR, TEMPLATES_DIR.parent):
    d.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# System prompt
# --------------------------------------------------------------------------- #
# Prompt único e estático — não há mais seções por "modo" (task `modes-1`).
# O bloco "Ferramentas disponíveis" abaixo é o que rodava em produção como
# `_PROMPT_CHAT` (o único modo que o classificador morto jamais deixou de
# selecionar, na prática); preservado tal como estava para não mudar
# comportamento, só a fachada em torno dele.
#
# Drift de data: a primeira linha (`Data atual: ...`) é computada UMA VEZ no
# import do módulo. Em processos long-running, a data fica velha (drift de até
# 24h é tolerável); para precisão de minutos/segundos, o agente usa
# `get_date_time_current` (que continua existindo, só perde centralidade).
_CURRENT_DATE: str = datetime.now(_resolve_tz()).date().isoformat()
_CURRENT_TZ: str = os.environ.get("JEFF_AI_TZ", "UTC")

_SYSTEM_PROMPT = f"""Data atual: {_CURRENT_DATE} ({_CURRENT_TZ})

Você é **Jeff AI**, um agente de desenvolvimento unificado no estilo
Claude Code / Hermes. Você é inteligente, direto, técnico e cuida do
usuário.

## Princípios
1. **Memória persistente**: você tem memória cross-thread, em duas camadas.
   Use `search_memory(query)` no início de uma resposta sempre que o usuário
   se referir a algo do passado ou perguntar "por que decidimos X" — ela
   busca nas duas camadas juntas. Salve fatos duráveis (preferências,
   convenções) com `save_memory`. Registre decisões não-óbvias e o
   raciocínio por trás delas com `log_episode` — depois de terminar uma
   tarefa relevante, ou quando o usuário corrigir uma ação sua. Pedido
   autocontido (sem referência ao passado) não precisa de busca — não pague
   esse custo à toa. Use `list_memories`/`delete_memory` se o usuário pedir
   para ver ou apagar algo da memória.
2. **Transparência**: explique o que vai fazer ANTES de tools pesadas
   (edits, commits, shell, geração de imagens).
3. **Respeite tiers de aprovação**: NÃO tente contornar `interrupt_on`.
4. **Datas**: data e hora atuais estão no topo deste prompt. Chame
   `get_date_time_current()` **apenas** se precisar de precisão de
   minutos/segundos (ex.: timestamp exato, logs, agendamento). Para data em
   formato dia, use a data no topo do prompt — não custa tool call.
5. **Imagens**: SEMPRE delegue para `image_design_subagent` (que tem
   gate de aprovação próprio). Nunca gere imagens diretamente.
6. **Documentos Office**: use as tools nativas (`create_docx_document`,
   `create_xlsx_spreadsheet`, `create_pptx_presentation`) — cada uma
    devolve `{{path, url, metadata}}`. Use SEMPRE `url` no markdown.
    SEMPRE popule `blocks` (docx) e as linhas de cada aba (xlsx) com o
    conteúdo real pedido pelo usuário — nunca chame `create_docx_document`
    com `blocks` vazio/omitido nem `create_xlsx_spreadsheet` com uma aba sem
    linhas; ambos os casos são rejeitados com `error`. Uma string simples
    não é mais um atalho válido para `create_docx_document` — a tool exige
    `DocxDocumentInput` estruturado.
7. **Auto-extensão**: skills em `/skills/<nome>/SKILL.md` (carregam ao
   vivo). Tools Python via `save_generated_tool` (precisa aprovação
   humana + restart).
8. **Edição de código** (quando ativa): tools de Tier 3 (edit_file,
   patch_file, multi_file_edit, git_commit) pausam o framework para
   aprovação humana com diff preview. Aprove SOMENTE se o diff
   estiver correto.
9. **Envelope de permissões**: ANTES de chamar qualquer tool de Tier 3+
   (edit_file, patch_file, multi_file_edit, git_commit, git_apply_commit,
   install_external_skill) ou Tier 4 (run_shell_command), chame
   `propose_envelope` pedindo as capabilities necessárias
   (`write_existing`, `vcs`, `shell`, `network`, ...) com uma
   justificativa de 1 linha cada, e declare em `excluded_capabilities`
   as que você NÃO precisa. `required_capabilities` é uma lista de
   objetos `{{"capability": ..., "justification": ...}}` — NUNCA
   `{{nome_da_capability: justificativa}}`. Exemplo correto:
   `required_capabilities=[{{"capability": "write_existing", "justification": "Editar main.py"}}]`.
   Tools de leitura/pesquisa (Tier 1) e criação de arquivo NOVO (Tier 2)
   não precisam disso — chamar sem propor
   envelope é normal para elas. Uma tool de Tier 3+/4 chamada SEM
   envelope concedido é BLOQUEADA antes de executar; se isso acontecer,
   chame `propose_envelope` pedindo a capability que faltou — não tente
   outra tool para o mesmo efeito, e não finja que a ação foi concluída.
10. **Diagramas**: ao explicar arquitetura, um fluxo com passos/decisões,
    uma sequência de chamadas entre sistemas, ou relacionamento entre
    entidades, prefira emitir um bloco ```mermaid``` (o frontend renderiza
    automaticamente como SVG inline) em vez de, ou além de, prosa. É só
    formatação de saída — sem tool call, sem gate de aprovação. Consulte a
    skill `diagram-creator` para os tipos de diagrama suportados e um guia
    de sintaxe.

## Diretórios
- Repositório real: `{REPO_ROOT}` (código-fonte)
- Workspace isolado: `{WORKSPACE_DIR}` (artefatos, scratch)
- Outputs: `{OUTPUTS_DIR}` (documentos de requisitos)
- SDD spec dir: `{SPECIFY_DIR}` (artefatos spec-kit)
- Skills: `{SKILLS_DIR}` (carregadas automaticamente)

## Ferramentas disponíveis

- **Memória de longo prazo** (TODAS as threads): `search_memory` no início
  quando o usuário se referir a contexto passado; `save_memory` para fatos
  duráveis (preferências, convenções) — NUNCA para texto longo (rejeitado
  acima de ~1000 chars); `log_episode` para registrar uma decisão e o
  raciocínio por trás dela; `list_memories`/`delete_memory` para auditar e
  remover entradas a pedido do usuário.
- **Memória de documentos** (páginas, artigos, livros inteiros):
  `ingest_document` para indexar um corpus de texto (chunking automático);
  `search_documents` para recuperar trechos relevantes depois. Use isto, e
  NÃO `save_memory`, sempre que o conteúdo for maior que um fato pontual.
- **Pesquisa externa**: `internet_search`, `search_arxiv`.
- **Geração de documentos**: `create_docx_document`, `create_xlsx_spreadsheet`,
  `create_pptx_presentation` (Tier 2 — execução direta, sem gate).
- **Imagens**: delegue para `image_design_subagent` (sempre).
- **Leitura do projeto**: `read_project_file`, `list_project_files`
  (somente leitura).
- **Shell**: `run_shell_command` (Tier 4 — interrupt + denylist).
"""


# --------------------------------------------------------------------------- #
# Tool registration
# --------------------------------------------------------------------------- #
# Lista unificada de todas as tools usadas pelos grafos legados + as novas
# (code/test/git). O deepagents aceita uma lista flat; subagentes fazem
# delegação via `task()` e não precisam de suas tools registradas no
# orquestrador (apenas os nomes importam).

_UNIFIED_TOOLS: list = [
    # --- Memória e utilidades ---------------------------------------------- #
    save_memory,
    search_memory,
    log_episode,
    list_memories,
    delete_memory,
    ingest_document,
    search_documents,
    get_date_time_current,
    # --- Pesquisa externa ------------------------------------------------- #
    internet_search,
    search_arxiv,
    # --- Imagens (referência) --------------------------------------------- #
    fetch_reference_image,
    check_reference_image,
    # --- Documentos Office (Tier 2) --------------------------------------- #
    create_docx_document,
    create_xlsx_spreadsheet,
    create_pptx_presentation,
    # --- Documentos Office/PDF (markitdown) --------------------------------- #
    # Substitui a change `document-reading-tools`. Tier 1 (auto): só leitura.
    read_document,
    # --- Self-extension (listagens, leitura, tools geradas) --------------- #
    list_project_files,
    read_project_file,
    save_generated_tool,
    list_generated_tools,
    find_external_skills,
    list_skills_in_repo,
    install_external_skill,
    *load_approved_tools(),
    # --- Shell (Tier 4) --------------------------------------------------- #
    run_shell_command,
    # --- Requirements (merge de artefatos) -------------------------------- #
    merge_generated_files,
    # --- SDD tools -------------------------------------------------------- #
    create_feature_directory,
    load_template,
    validate_artifact,
    get_sdd_state,
    get_next_feature_number,
    # --- Code editing (Tier 3) -------------------------------------------- #
    edit_file,
    patch_file,
    multi_file_edit,
    grep_project,
    # --- Tests (Tier 1) --------------------------------------------------- #
    run_tests,
    # --- Git (Tier 1 read, Tier 3 commit) --------------------------------- #
    git_status,
    git_diff,
    git_commit,
    git_apply_commit,
    git_branch,
    # --- Envelope de permissões (task envelope-7) -------------------------- #
    propose_envelope_tool,
]


# Subagentes registrados no grafo unificado. Reduzido de 9 -> 1 na task
# `skills-4`: `fullstack_subagent` e os 7 subagentes de fase SDD foram
# deletados — SDD e requisitos são entregues como skills
# (`backend/skills/{sdd,requirements}/SKILL.md`), com paridade de output
# confirmada em `skills-3-rerun` (design, Addendum 3). `image_design_subagent`
# é a única exceção legítima: contexto isolado, gate `interrupt_on` próprio
# e memória de estilo por thread.
_UNIFIED_SUBAGENTS: list = [
    image_design_subagent,
]


# --------------------------------------------------------------------------- #
# Backend factory unificado (CompositeBackend com 6 rotas)
# --------------------------------------------------------------------------- #
# A rota `/memories/` é SEMPRE montada. Antes ela era condicionada ao "modo" do
# grafo, mas o sistema de modos nunca existiu de fato — tudo era construído como
# `chat`, e `chat` não estava na lista de modos que "precisavam" de memória.
# Resultado: a rota ficava desmontada em todos os grafos.
#
# NOTA: isso NÃO é o mesmo que "a memória estava desligada". As tools
# `save_memory` / `search_memory` usam `get_store()` — o store do LangGraph,
# injetado pelo runtime via `langgraph.json` — e sempre funcionaram,
# independentemente daqui. O que faltava era o acesso *filesystem* à memória
# (`ls` / `read_file` sobre `/memories/`).

def _build_backend_factory():
    """Constrói a `backend_factory` unificada.

    Rotas:
    - `/workspace/` → WORKSPACE_DIR (per-thread, scratch/artifacts)
    - `/repo/`      → REPO_ROOT      (shared, código real)
    - `/outputs/`   → OUTPUTS_DIR    (per-thread, requirements)
    - `/specify/`   → SPECIFY_DIR    (shared, SDD scaffolding)
    - `/skills/`    → SKILLS_DIR     (shared, skills carregadas pelo deepagents)
    - `/memories/`  → StoreBackend   (cross-thread, sempre montada)
    """
    return make_backend_factory(
        routes=[
            FsRoute(prefix=f"{WORKSPACE_DIR}", base_dir=WORKSPACE_DIR, per_thread=True),
            FsRoute(prefix=f"{REPO_ROOT}",    base_dir=REPO_ROOT),
            FsRoute(prefix=f"{OUTPUTS_DIR}",  base_dir=OUTPUTS_DIR, per_thread=True),
            FsRoute(
                prefix=f"{SPECIFY_DIR}",
                base_dir=SPECIFY_DIR,
                ensure_subpath="specs",
            ),
            FsRoute(prefix=f"{TEMPLATES_DIR}", base_dir=TEMPLATES_DIR),
            FsRoute(prefix="/skills/",         base_dir=SKILLS_DIR),
        ],
        include_store=True,
    )


# --------------------------------------------------------------------------- #
# `interrupt_on`
# --------------------------------------------------------------------------- #
# Computado uma vez no import deste módulo, a partir das tools REAIS registradas.
# O `build_interrupt_on` recebe a lista de NOMES e classifica cada um pelo tier
# do `TIER_REGISTRY` (deny-by-default: `UNKNOWN_TOOL_TIER = 3`); qualquer tool
# que não esteja explicitamente em Tier 1 ou 2 entra no gate — inclusive as que
# o registry nunca viu. Por isso uma tool fora do registry SEMPRE executa
# atrás de `interrupt_on` (foi exatamente o que faltou no `git_apply_commit`
# antes da task `floor-4` corrigir). O `_UNIFIED_TOOLS` aqui é o set base
# (NATIVO); tools MCP carregadas em runtime pelo `McpToolsMiddleware` herdam o
# mesmo deny-by-default e o `EnvelopeMiddleware.wrap_tool_call` bloqueia
# qualquer tool fora do envelope **antes** de HITL ser consultado.
_TOOL_NAMES: list[str] = [
    getattr(t, "name", None) or getattr(t, "__name__", "") for t in _UNIFIED_TOOLS
]
_interrupt_on = build_interrupt_on(_TOOL_NAMES)


# --------------------------------------------------------------------------- #
# Construção do grafo
# --------------------------------------------------------------------------- #
def build_unified():
    """Constrói o grafo `unified`. Usado no import deste módulo e por testes.

    O retorno é um grafo LangGraph configurado com `recursion_limit=1000`.

    `middleware=[EnvelopeLifecycleMiddleware(), EnvelopeMiddleware()]` liga o
    harness de permissões por tarefa (task `envelope-7`) — antes disso,
    `envelope-1..6` existiam completos e testados, mas isolados de qualquer
    grafo real. Aditivo por design (Decision D1): remover a lista
    `middleware=[...]` restaura o comportamento anterior sem tocar em mais
    nada. `EnvelopeMiddleware()` sem argumento começa com `granted=set()` —
    deny-all acima do piso, o caso mais restritivo (REQ-002).

    `ScopedSkillsMiddleware` substitui o `skills=[...]` do `create_deep_agent`
    (task `ctx-2`, design Q8): a `SkillsMiddleware` padrão do deepagents lista
    as 11 skills inteiras em todo turno; a variante escopada só injeta as
    relevantes à conversa. Passada explicitamente em `middleware=[...]` em vez
    do atalho `skills=` para poder trocar a classe sem mexer no resto.
    """
    backend_factory = _build_backend_factory()
    graph = create_deep_agent(
        model=unified_model,
        subagents=_UNIFIED_SUBAGENTS,
        tools=_UNIFIED_TOOLS,
        system_prompt=_SYSTEM_PROMPT,
        interrupt_on=_interrupt_on,
        backend=backend_factory,
        middleware=[
            EnvelopeLifecycleMiddleware(),
            McpToolsMiddleware(),
            EnvelopeMiddleware(),
            ScopedSkillsMiddleware(backend=backend_factory, sources=["/skills/"]),
        ],
    )
    return graph.with_config({"recursion_limit": 1000})


# Grafo default usado quando o LangGraph API sobe o `unified`. Um
# `configurable.mode` que um frontend antigo ainda envie em tempo de invoke
# é ignorado silenciosamente — nada aqui lê essa chave.
unified = build_unified()


__all__ = [
    "build_unified",
    "unified",
]
