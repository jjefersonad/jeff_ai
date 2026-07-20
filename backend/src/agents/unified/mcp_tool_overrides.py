"""Classificação manual de capacidade para tools MCP de terceiros.

Cobre a task `unified-agent-realignment-task-mcp-3` (Q3 do design da
`unified-agent-realignment`, REQ-003 do `mcp-client`).

## Por que isto existe

`effects.TOOL_EFFECTS` é um registry estático em código — auditável, mas
não pode conter tools de servidores MCP de terceiros, que só existem em
runtime. Por padrão, toda tool MCP sem classificação aqui cai em
`Capability.NETWORK` (piso, sem gate — decisão explícita do usuário na
change `remove-mcp-unknown-failsafe`). Este módulo existe para quem quiser
o oposto: restringir manualmente uma tool MCP específica a uma capability
mais estrita (`write_existing`, `vcs`, `shell`), quando o piso `NETWORK`
sub-representa o efeito real dela.

## A classificação é um ato HUMANO

Este módulo só é chamado pela API administrativa (`mcp_admin_api.py`),
servida pelo `image_server.py` — um processo HTTP separado do grafo do
agente. **Nenhuma tool do agente escreve neste arquivo.** É assim que a
regra "nenhuma heurística do agente pode rebaixar a capacidade de uma
tool" (task-mcp-3, último critério de aceite) é satisfeita por construção:
o agente não tem, e não pode ganhar, acesso de escrita a
`mcp_tool_overrides.json` através de nenhuma tool registrada nele.

## Formato de `mcp_tool_overrides.json`

```json
{
  "mcp__meu_servidor__read_status": "read"
}
```

Chave: nome QUALIFICADO da tool MCP (`mcp__<servidor>__<tool>`, o mesmo
formato produzido por `mcp_tools_middleware._qualify_tool_names`). Valor:
um dos nomes de `effects.CAPABILITY_NAMES`.
"""
from __future__ import annotations

import json
from pathlib import Path

# backend/mcp_tool_overrides.json — ao lado de backend/mcp_servers.json.
DEFAULT_OVERRIDES_PATH = Path(__file__).resolve().parents[3] / "mcp_tool_overrides.json"

# Prefixo que identifica uma tool como vinda de um servidor MCP
# (`mcp_tools_middleware._qualify_tool_names`). Overrides só se aplicam a
# tools com este prefixo — classificar uma tool NATIVA por aqui não faz
# sentido (ela já tem uma entrada auditável em `TOOL_EFFECTS`).
MCP_TOOL_PREFIX = "mcp__"


class McpOverrideError(ValueError):
    """Override de capacidade inválido (tool não é MCP, capacidade desconhecida)."""


def load_overrides(path: Path | str = DEFAULT_OVERRIDES_PATH) -> dict[str, str]:
    """Lê `mcp_tool_overrides.json`. Arquivo ausente → `{}` (nenhum override).

    Devolve o mapeamento cru `{tool_name: capability_value}` — a validação
    de que `capability_value` é um `Capability` válido é responsabilidade
    do caller (`effects.classify`), para evitar import circular
    (`effects.py` importaria este módulo, não o contrário).
    """
    config_path = Path(path)
    if not config_path.exists():
        return {}
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def get_override(tool_name: str, path: Path | str = DEFAULT_OVERRIDES_PATH) -> str | None:
    """Devolve a capacidade classificada manualmente para `tool_name`, ou `None`."""
    return load_overrides(path).get(tool_name)


def set_override(
    tool_name: str,
    capability: str,
    *,
    valid_capabilities: tuple[str, ...],
    path: Path | str = DEFAULT_OVERRIDES_PATH,
) -> dict[str, str]:
    """Grava a classificação manual de `tool_name` como `capability`.

    Args:
        tool_name: nome QUALIFICADO da tool MCP (deve começar com `mcp__`).
        capability: um dos valores em `valid_capabilities`.
        valid_capabilities: passado pelo caller (`effects.CAPABILITY_NAMES`)
            para não acoplar este módulo a `effects.py`.
        path: caminho do arquivo de overrides.

    Raises:
        McpOverrideError: `tool_name` não é uma tool MCP qualificada, ou
            `capability` não é uma capacidade válida.

    Returns:
        O dicionário de overrides completo, já persistido.
    """
    if not tool_name.startswith(MCP_TOOL_PREFIX):
        raise McpOverrideError(
            f"'{tool_name}' não é uma tool MCP qualificada (esperado prefixo "
            f"'{MCP_TOOL_PREFIX}'). Só tools MCP podem ser classificadas manualmente."
        )
    if capability not in valid_capabilities:
        raise McpOverrideError(
            f"capacidade '{capability}' inválida. Esperado uma de: {valid_capabilities}."
        )

    overrides = load_overrides(path)
    overrides[tool_name] = capability
    config_path = Path(path)
    config_path.write_text(json.dumps(overrides, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return overrides


def remove_override(tool_name: str, path: Path | str = DEFAULT_OVERRIDES_PATH) -> dict[str, str]:
    """Remove a classificação manual de `tool_name` (reverte para `unknown`).

    Não é erro remover um override que não existe — idempotente.
    """
    overrides = load_overrides(path)
    overrides.pop(tool_name, None)
    config_path = Path(path)
    config_path.write_text(json.dumps(overrides, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return overrides


__all__ = [
    "DEFAULT_OVERRIDES_PATH",
    "MCP_TOOL_PREFIX",
    "McpOverrideError",
    "get_override",
    "load_overrides",
    "remove_override",
    "set_override",
]
