"""Testes de `mcp_tool_overrides` (task `unified-agent-realignment-task-mcp-3`).

Cobre a classificação manual de capacidade de tools MCP (Q3 do design,
REQ-003 do `mcp-client`) e a integração com `effects.classify`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agents.unified.effects import CAPABILITY_NAMES, Capability, classify
from src.agents.unified.mcp_tool_overrides import (
    McpOverrideError,
    get_override,
    load_overrides,
    remove_override,
    set_override,
)


def test_missing_overrides_file_returns_empty(tmp_path: Path) -> None:
    assert load_overrides(tmp_path / "missing.json") == {}


def test_set_override_persists_and_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "overrides.json"
    set_override(
        "mcp__meu_servidor__read_status",
        "read",
        valid_capabilities=CAPABILITY_NAMES,
        path=path,
    )
    assert get_override("mcp__meu_servidor__read_status", path=path) == "read"
    assert json.loads(path.read_text()) == {"mcp__meu_servidor__read_status": "read"}


def test_set_override_rejects_non_mcp_tool_name(tmp_path: Path) -> None:
    """Só tools MCP qualificadas podem ser classificadas manualmente —
    classificar uma tool nativa por aqui não faz sentido (ela já tem
    entrada auditável em TOOL_EFFECTS)."""
    with pytest.raises(McpOverrideError, match="não é uma tool MCP"):
        set_override(
            "edit_file", "read", valid_capabilities=CAPABILITY_NAMES, path=tmp_path / "o.json"
        )


def test_set_override_rejects_invalid_capability(tmp_path: Path) -> None:
    with pytest.raises(McpOverrideError, match="inválida"):
        set_override(
            "mcp__srv__tool",
            "not-a-real-capability",
            valid_capabilities=CAPABILITY_NAMES,
            path=tmp_path / "o.json",
        )


def test_remove_override_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "overrides.json"
    remove_override("mcp__srv__tool", path=path)  # não existe — não deve levantar
    set_override(
        "mcp__srv__tool", "read", valid_capabilities=CAPABILITY_NAMES, path=path
    )
    remove_override("mcp__srv__tool", path=path)
    assert get_override("mcp__srv__tool", path=path) is None


# =========================================================================== #
# Integração com effects.classify()
# =========================================================================== #
def test_classify_uses_override_for_unqualified_mcp_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uma tool MCP fora do TOOL_EFFECTS estático recebe a capability
    classificada manualmente, não UNKNOWN."""
    import functools

    import src.agents.unified.mcp_tool_overrides as overrides_module

    override_path = tmp_path / "mcp_tool_overrides.json"
    set_override(
        "mcp__meu_servidor__read_status",
        "read",
        valid_capabilities=CAPABILITY_NAMES,
        path=override_path,
    )
    # `effects._mcp_manual_override` importa `get_override` de dentro da
    # função a cada chamada (lazy import) — é assim que monkeypatchar o
    # atributo do módulo aqui tem efeito sem reload. Monkeypatchar só
    # `DEFAULT_OVERRIDES_PATH` NÃO funcionaria: o default de `get_override`
    # já foi resolvido em tempo de definição da função.
    monkeypatch.setattr(
        overrides_module,
        "get_override",
        functools.partial(overrides_module.get_override, path=override_path),
    )

    assert classify("mcp__meu_servidor__read_status") == (Capability.READ,)


def test_classify_defaults_to_network_for_mcp_tool_without_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Desde `remove-mcp-unknown-failsafe`: tool MCP sem override cai em
    `NETWORK` (piso), não mais `UNKNOWN` — decisão explícita do usuário,
    escopada só a tools MCP (prefixo `mcp__`)."""
    import functools

    import src.agents.unified.mcp_tool_overrides as overrides_module

    override_path = tmp_path / "mcp_tool_overrides.json"
    monkeypatch.setattr(
        overrides_module,
        "get_override",
        functools.partial(overrides_module.get_override, path=override_path),
    )
    assert classify("mcp__meu_servidor__unclassified_tool") == (Capability.NETWORK,)


def test_classify_manual_override_still_wins_over_network_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O default `NETWORK` só se aplica na AUSÊNCIA de override — uma
    classificação manual explícita (ex.: `write_existing`, mais restrita)
    continua tendo precedência."""
    import functools

    import src.agents.unified.mcp_tool_overrides as overrides_module

    override_path = tmp_path / "mcp_tool_overrides.json"
    monkeypatch.setattr(
        overrides_module,
        "get_override",
        functools.partial(overrides_module.get_override, path=override_path),
    )
    set_override(
        "mcp__meu_servidor__delete_records",
        "write_existing",
        valid_capabilities=CAPABILITY_NAMES,
        path=override_path,
    )
    assert classify("mcp__meu_servidor__delete_records") == (Capability.WRITE_EXISTING,)


def test_classify_ignores_override_for_non_mcp_tool_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Um override gravado por engano sob um nome não-mcp__ nunca é
    consultado — `classify` só olha overrides para tools `mcp__*`."""
    import functools

    import src.agents.unified.mcp_tool_overrides as overrides_module

    override_path = tmp_path / "mcp_tool_overrides.json"
    override_path.write_text(json.dumps({"some_unknown_native_tool": "read"}))
    monkeypatch.setattr(
        overrides_module,
        "get_override",
        functools.partial(overrides_module.get_override, path=override_path),
    )

    assert classify("some_unknown_native_tool") == (Capability.UNKNOWN,)
