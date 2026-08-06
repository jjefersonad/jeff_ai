"""Tests for the diagnostic tool `list_mcp_servers_status` (task-tool-diagnostic-1
of the change `fix-mcp-tool-not-exposed-error`).

Covers both (1) the tool function returning `last_load_status` faithfully
and read-only, and (2) the tool being registered as Tier 1 (auto-approved) in
the `TIER_REGISTRY` so the agent can call it without going through the
approval gate.
"""
from __future__ import annotations

import pytest

import src.agents.unified.tier_config as tier_config_module
from src.agents.unified.mcp_tools_middleware import McpToolsMiddleware
from src.tools.list_mcp_servers_status import (
    LIST_MCP_SERVERS_STATUS_DESCRIPTION,
    LIST_MCP_SERVERS_STATUS_NAME,
    list_mcp_servers_status,
)


# --------------------------------------------------------------------------- #
# unit-1: returns last_load_status faithfully + read-only
# --------------------------------------------------------------------------- #
def test_list_mcp_servers_status_returns_last_load_status_readonly() -> None:
    """REQ-002: when the provider returns a populated dict, the tool
    MUST serialise that dict to JSON faithfully (no transformation,
    no truncation) AND MUST NOT mutate the input object.

    Uses `set_status_provider` to inject the snapshot — production code
    wires this up in `agent.py` at boot."""
    sample = {
        "loaded_at": "2026-08-05T17:30:00+00:00",
        "servers": {
            "zernio": {"configured": True, "connected": True, "tool_count": 2, "last_error": None},
            "gmail": {"configured": True, "connected": False, "tool_count": 0, "last_error": "<credential-redacted>"},
        },
        "tools_by_name": {
            "mcp__zernio__posts_list": "zernio",
            "mcp__zernio__posts_delete": "zernio",
        },
    }
    import src.tools.list_mcp_servers_status as mod

    mod.set_status_provider(lambda: sample)
    try:
        out = mod.list_mcp_servers_status.invoke({})
    finally:
        mod.set_status_provider(lambda: {})
    # A tool devolve JSON; parse e compara
    import json as _json
    parsed = _json.loads(out)
    assert parsed == sample


def test_list_mcp_servers_status_is_pure_no_mutation() -> None:
    """Garantia reforçada: a tool NÃO muta o dict de origem. A
    implementação usa `copy.deepcopy` defensivamente."""
    import src.tools.list_mcp_servers_status as mod

    obj = {
        "loaded_at": "2026-08-05T17:30:00+00:00",
        "servers": {"srv": {"configured": True, "connected": True, "tool_count": 1, "last_error": None}},
        "tools_by_name": {"mcp__srv__t": "srv"},
    }
    snapshot = repr(obj)
    mod.set_status_provider(lambda: obj)
    try:
        mod.list_mcp_servers_status.invoke({})
    finally:
        mod.set_status_provider(lambda: {})

    assert repr(obj) == snapshot, "list_mcp_servers_status MUST be read-only"


# --------------------------------------------------------------------------- #
# unit-2: registered as Tier 1
# --------------------------------------------------------------------------- #
def test_list_mcp_servers_status_is_tier_1() -> None:
    """REQ-002 (Decision 4 do design): a tool MUST estar no Tier 1 do
    `TIER_REGISTRY` — auto-aprovada, sem gate. Crítico porque o agente
    precisa poder chamá-la sem precisar de aprovação humana, mesmo
    durante o debugging."""
    tier = tier_config_module.get_tier(LIST_MCP_SERVERS_STATUS_NAME)
    assert tier == 1, (
        f"list_mcp_servers_status MUST be tier 1 (auto-approved), got {tier}"
    )
    # também verificar que aparece no Tier 1 set para Tier 2==3 stand-in no test
    assert LIST_MCP_SERVERS_STATUS_NAME in tier_config_module.TIER_1_TOOLS


# --------------------------------------------------------------------------- #
# Description sanity
# --------------------------------------------------------------------------- #
def test_list_mcp_servers_status_description_warns_about_diagnosis() -> None:
    """A descrição da tool MUST mencionar diagnóstico de tools `mcp__*`
    indisponíveis — assim o modelo sabe quando usá-la."""
    desc_lower = LIST_MCP_SERVERS_STATUS_DESCRIPTION.lower()
    assert "diagnóstico" in desc_lower or "diagnostic" in desc_lower
    assert "mcp__" in LIST_MCP_SERVERS_STATUS_DESCRIPTION
    assert "categoria" in desc_lower or "categorize" in desc_lower
