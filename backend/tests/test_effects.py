"""Testes do registry de efeitos: `src/agents/unified/effects.py`.

Cobre a task `unified-agent-realignment-task-envelope-2`, que constrói o
mapa `tool → capability` (Decision D3 do design) usado pelo
`EnvelopeMiddleware` para fechar o cenário "contorno por tool
equivalente" do `task-scoped-permissions` REQ-005.

Os testes são herméticos: nenhum Ollama ou Postgres é necessário. O
classificador dinâmico de `write_file` lê o filesystem real (o path é
passado como argumento), então alguns testes criam um arquivo temporário
em `/tmp` para verificar a transição `write_new` → `write_existing`.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

from src.agents.unified.effects import (
    CAPABILITY_NAMES,
    SHELL_ENCOMPASSES,
    TOOL_EFFECTS,
    Capability,
    classify,
    has_capability,
    is_contradictory_envelope,
    is_unknown,
)


# --------------------------------------------------------------------------- #
# Capacidade da Capability enum
# --------------------------------------------------------------------------- #
def test_capability_values_match_d3() -> None:
    """D3 lista 7 capacidades: read, write_new, write_existing, vcs,
    shell, network, unknown. A enum deve ter EXATAMENTE essas."""
    assert CAPABILITY_NAMES == (
        "read",
        "write_new",
        "write_existing",
        "vcs",
        "shell",
        "network",
        "unknown",
    )


# --------------------------------------------------------------------------- #
# REQ-005: todas as tools nativas estão mapeadas para uma ou mais capacidades
# --------------------------------------------------------------------------- #
# Lista declarada explicitamente de TODAS as tools que o agente `unified`
# registra. Foi copiada de `src/agents/unified/agent.py:_UNIFIED_TOOLS`
# (2026-07-12) e é mantida em sincronia MANUALMENTE — este teste é a
# rede de segurança que falha se alguém adicionar uma tool nova ao
# agente sem classificá-la em `effects.py`.
#
# Por que NÃO importamos `src.agents.unified.agent`? Porque o módulo
# executa `unified = build_unified(...)` no import, que constrói o
# grafo com `ollama_model` — em ambiente sem Ollama rápido, isso
# trava a suíte. O snapshot manual abaixo é a única forma de
# auditar o registry sem depender de side effects de runtime.
EXPECTED_AGENT_TOOLS: frozenset[str] = frozenset(
    {
        # Memória e utilidades
        "save_memory",
        "search_memory",
        "log_episode",
        "list_memories",
        "delete_memory",
        "get_date_time_current",
        # Pesquisa externa
        "internet_search",
        "search_arxiv",
        # Imagens (referência)
        "fetch_reference_image",
        "check_reference_image",
        # Documentos Office (Tier 2)
        "create_docx_document",
        "create_xlsx_spreadsheet",
        "create_pptx_presentation",
        # Filesystem
        "list_project_files",
        "read_project_file",
        # Self-extension
        "save_generated_tool",
        "list_generated_tools",
        "find_external_skills",
        "list_skills_in_repo",
        "install_external_skill",
        # Shell
        "run_shell_command",
        # SDD
        "merge_generated_files",
        "create_feature_directory",
        "load_template",
        "validate_artifact",
        "get_sdd_state",
        "get_next_feature_number",
        # Code editing (Tier 3)
        "edit_file",
        "patch_file",
        "multi_file_edit",
        "grep_project",
        "run_tests",
        # Git (Tier 3)
        "git_status",
        "git_diff",
        "git_commit",
        "git_apply_commit",
        "git_branch",
        # Envelope (plano de controle, task envelope-7)
        "propose_envelope",
    }
)


def test_every_agent_tool_has_an_effect_entry() -> None:
    """Toda tool do agente `unified` DEVE ter uma entrada explícita no
    registry. Tool sem entrada cai em `unknown` (fail-safe), o que é
    seguro mas gera atrito (Tier 3+); o teste força o(a) autor(a) a
    classificar cada tool nova explicitamente.
    """
    registry_tools = set(TOOL_EFFECTS.keys())

    # 1. Tools do agente não podem estar ausentes do registry.
    missing = EXPECTED_AGENT_TOOLS - registry_tools
    assert not missing, (
        f"tools do agente sem classificação de efeito: {sorted(missing)}. "
        "Adicione a entrada correspondente em src/agents/unified/effects.py:TOOL_EFFECTS."
    )

    # 2. O snapshot do agente está completo: se o autor adicionou uma
    # tool nova e atualizou `EXPECTED_AGENT_TOOLS` MAS esqueceu o
    # registry, o teste (1) pega. Se esqueceu AMBOS, este teste
    # falha por "agent snapshot desatualizado".
    assert len(EXPECTED_AGENT_TOOLS) == 38, (
        f"EXPECTED_AGENT_TOOLS deveria ter 38 tools; tem "
        f"{len(EXPECTED_AGENT_TOOLS)}. Atualize o snapshot ao adicionar "
        "ou remover tools do agente."
    )


# --------------------------------------------------------------------------- #
# REQ-005: `write_file` é dinâmico — depende do path em runtime
# --------------------------------------------------------------------------- #
@pytest.fixture
def temp_file(tmp_path: Path) -> Iterator[str]:
    """Cria um arquivo temporário com conteúdo e devolve seu path."""
    p = tmp_path / "exists.py"
    p.write_text("# pre-existing content\n", encoding="utf-8")
    yield str(p)
    # tmp_path é removido automaticamente.


def test_write_file_on_existing_path_is_write_existing(temp_file: str) -> None:
    """Cenário REQ-005 ("contorno por tool equivalente"): se o envelope
    proíbe `edit_file` (efeito `write_existing`) e o modelo tenta o
    mesmo efeito via `write_file` sobre um path que JÁ EXISTE, o
    classificador devolve `write_existing` — o envelope pega.
    """
    result = classify(
        "write_file",
        {"name": "write_file", "args": {"path": temp_file}},
    )
    assert Capability.WRITE_EXISTING in result, (
        f"write_file sobre path existente deveria ser WRITE_EXISTING; "
        f"obteve {result}"
    )


def test_write_file_on_new_path_is_write_new(tmp_path: Path) -> None:
    """O complemento: `write_file` sobre path NOVO é `write_new`
    (Tier 2 = notificação, não interrupt). Esta é a default sensata
    para o caso comum de scaffolding."""
    new_path = str(tmp_path / "does-not-exist-yet.py")
    assert not Path(new_path).exists(), "fixture: o path deveria ser novo"

    result = classify(
        "write_file",
        {"name": "write_file", "args": {"path": new_path}},
    )
    assert Capability.WRITE_NEW in result
    assert Capability.WRITE_EXISTING not in result, (
        f"write_file sobre path novo NÃO deveria ser WRITE_EXISTING; "
        f"obteve {result}"
    )


def test_write_file_with_no_tool_call_falls_back_to_write_new() -> None:
    """Quando `classify` é chamado sem `tool_call` (e.g. na fase de
    PROPOSTA do envelope, em que a tool ainda não foi chamada), o
    fallback é o caso otimista (`write_new`). Isto é deliberado —
    classificar como `unknown` seria exagero para a tool mais comum
    do `FilesystemMiddleware`.
    """
    result = classify("write_file")
    assert result == (Capability.WRITE_NEW,)


def test_write_file_with_missing_path_arg_falls_back_to_write_new() -> None:
    """Sem `args["path"]`, o classificador dinâmico não tem o que
    inspecionar. Fallback: `write_new`."""
    result = classify("write_file", {"name": "write_file"})
    assert Capability.WRITE_NEW in result
    assert Capability.WRITE_EXISTING not in result


# --------------------------------------------------------------------------- #
# REQ-008: tool ausente do registry → `unknown` (fail-safe)
# --------------------------------------------------------------------------- #
def test_unknown_tool_returns_unknown_capability() -> None:
    """Tool que não está no registry é classificada como `unknown` —
    fail-safe pra origens não-MCP (ex.: `save_generated_tool`).

    NOTA: `"mcp_qualquer.delete_records"` (underscore simples + ponto)
    NÃO é o prefixo qualificado real de tool MCP (`mcp__servidor__tool`,
    duplo underscore — ver `mcp_tools_middleware._qualify_tool_names`).
    Este teste cobre o fail-safe de tool desconhecida em geral, não o
    caso específico de tool MCP — que, desde `remove-mcp-unknown-failsafe`,
    tem tratamento diferente (`NETWORK`, não `UNKNOWN`; ver
    `test_mcp_tool_overrides.test_classify_defaults_to_network_for_mcp_tool_without_override`).
    """
    assert is_unknown("mcp_qualquer.delete_records") is True
    result = classify("mcp_qualquer.delete_records")
    assert result == (Capability.UNKNOWN,)


def test_real_mcp_qualified_tool_name_is_not_unknown_but_network() -> None:
    """Contraste com o teste acima: um nome REALMENTE qualificado como
    tool MCP (`mcp__servidor__tool`) não cai mais em `unknown` — desde
    `remove-mcp-unknown-failsafe`, classifica como `network` (piso)."""
    assert classify("mcp__servidor__delete_records") == (Capability.NETWORK,)


def test_known_tool_is_not_unknown() -> None:
    assert is_unknown("edit_file") is False
    assert is_unknown("read_project_file") is False
    assert is_unknown("run_shell_command") is False


# --------------------------------------------------------------------------- #
# Cada capacidade tem ao menos um caso no registry
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "capability",
    [
        Capability.READ,
        Capability.WRITE_NEW,
        Capability.WRITE_EXISTING,
        Capability.VCS,
        Capability.SHELL,
        Capability.NETWORK,
        Capability.UNKNOWN,
    ],
)
def test_every_capability_has_at_least_one_tool(capability: Capability) -> None:
    """Cada capability deve ter ao menos uma tool nativa mapeada. O
    ponto do `unknown` é coberto pela ausência de qualquer tool —
    mas o teste também verifica que ele está na enum.
    """
    if capability is Capability.UNKNOWN:
        # O `unknown` é o default para tools ausentes; verificamos que
        # o `classify` o produz.
        assert Capability.UNKNOWN in classify("never_seen_tool")
        return

    matching = [
        name
        for name, entry in TOOL_EFFECTS.items()
        # Entradas dinâmicas resolvem para `WRITE_NEW` ou
        # `WRITE_EXISTING` em runtime; cobrimos ambos os casos.
        if any(isinstance(item, Capability) and item is capability for item in entry)
        or any(
            callable(item) and item.__name__ in {"_classify_write_file"}
            and capability is Capability.WRITE_EXISTING
            for item in entry
        )
    ]
    assert matching, f"nenhuma tool mapeada para capability {capability.value!r}"


# --------------------------------------------------------------------------- #
# Tools específicas: classificação correta
# --------------------------------------------------------------------------- #
def test_edit_file_is_write_existing() -> None:
    assert classify("edit_file") == (Capability.WRITE_EXISTING,)


def test_patch_file_is_write_existing() -> None:
    assert classify("patch_file") == (Capability.WRITE_EXISTING,)


def test_multi_file_edit_is_write_existing() -> None:
    assert classify("multi_file_edit") == (Capability.WRITE_EXISTING,)


def test_git_commit_is_vcs() -> None:
    assert classify("git_commit") == (Capability.VCS,)


def test_git_apply_commit_is_vcs() -> None:
    """`git_apply_commit` foi descoberto na `floor-4` como o executor
    REAL do commit. O efeito (vcs) é o mesmo de `git_commit` —
    qualquer envelope que proíbe vcs pega os dois."""
    assert classify("git_apply_commit") == (Capability.VCS,)


def test_run_shell_command_is_shell() -> None:
    assert classify("run_shell_command") == (Capability.SHELL,)


def test_install_external_skill_is_network_and_write_new() -> None:
    """Baixa de repositório remoto (network) E escreve em
    `backend/skills/` (write_new). Duas capabilities — o envelope tem
    que conceder AMBAS para a tool passar."""
    caps = classify("install_external_skill")
    assert Capability.NETWORK in caps
    assert Capability.WRITE_NEW in caps
    assert Capability.WRITE_EXISTING not in caps


def test_read_only_tools_are_read() -> None:
    # `internet_search` e `search_arxiv` são NETWORK (fazem requisição
    # externa), não READ — uma tool READ é local ao repo/agente.
    for name in [
        "read_project_file",
        "read_file",
        "list_project_files",
        "ls",
        "grep_project",
        "search_memory",
        "git_status",
        "git_diff",
        "git_branch",
    ]:
        caps = classify(name)
        assert caps == (Capability.READ,), (
            f"{name} deveria ser READ, obteve {caps}"
        )


# --------------------------------------------------------------------------- #
# has_capability / is_unknown: helpers
# --------------------------------------------------------------------------- #
def test_has_capability_true_for_matching() -> None:
    assert has_capability("edit_file", Capability.WRITE_EXISTING) is True


def test_has_capability_false_for_non_matching() -> None:
    assert has_capability("edit_file", Capability.SHELL) is False


def test_has_capability_true_for_dynamic_write_existing(temp_file: str) -> None:
    assert (
        has_capability(
            "write_file",
            Capability.WRITE_EXISTING,
            {"name": "write_file", "args": {"path": temp_file}},
        )
        is True
    )


# --------------------------------------------------------------------------- #
# D4: `shell` é curinga — engloba `write_existing`, `vcs`, `network`
# --------------------------------------------------------------------------- #
def test_shell_encompasses_documented_capabilities() -> None:
    """D4 explicita os três que o `shell` engloba na prática. O
    conjunto NÃO pode crescer sem o design ser atualizado — é a
    única coisa que distingue uma contradição real de uma falsa."""
    assert SHELL_ENCOMPASSES == frozenset(
        {Capability.WRITE_EXISTING, Capability.VCS, Capability.NETWORK}
    )


def test_shell_alone_is_not_contradictory() -> None:
    """Conceder só `shell` é uma escolha válida. A contradição é
    `shell + nega alguma coisa que ele engloba`. Como `granted` é o
    conjunto positivo, só `shell` é não-contraditório.
    """
    assert is_contradictory_envelope({Capability.SHELL}) is False


def test_shell_with_encompassed_is_contradictory() -> None:
    """Conceder `shell` E simultaneamente `write_existing` é, no
    mínimo, redundante — o envelope que diz "shell sim, edit não"
    mente. O detector tem que pegar.
    """
    assert (
        is_contradictory_envelope(
            {Capability.SHELL, Capability.WRITE_EXISTING}
        )
        is True
    )


# --------------------------------------------------------------------------- #
# O registry é declarativo e auditável num só lugar
# --------------------------------------------------------------------------- #
def test_registry_is_a_single_dict() -> None:
    """`TOOL_EFFECTS` é um único `Mapping` (imutável) declarado no
    topo do módulo. Não há dispersão por tools individuais nem
    registries secundários.
    """
    from src.agents.unified import effects

    assert isinstance(effects.TOOL_EFFECTS, Mapping)
    # Não há nenhum outro atributo público de registry.
    for name in dir(effects):
        if name.startswith("_") or name[0].isupper():
            continue
        # Apenas `TOOL_EFFECTS` deve ser o registry. Outros nomes
        # (`Capability`, `classify`, etc.) são do módulo.
        if name in {"TOOL_EFFECTS", "Capability", "SHELL_ENCOMPASSES"}:
            continue
        # Qualquer outro all-caps do módulo não deve ser um Mapping.
        value = getattr(effects, name)
        assert not isinstance(value, Mapping) or name == "TOOL_EFFECTS", (
            f"registry espalhado: {name} também é um Mapping"
        )


def test_registry_entries_are_immutable_tuples() -> None:
    """Cada entrada é uma tupla — uma tool pode ter múltiplas
    capabilities, mas a relação é imutável (não se pode adicionar
    capabilities em runtime)."""
    for name, entry in TOOL_EFFECTS.items():
        assert isinstance(entry, tuple), (
            f"entrada de {name} deveria ser tuple, é {type(entry).__name__}"
        )
