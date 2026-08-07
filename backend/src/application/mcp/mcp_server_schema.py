"""Validação de escrita para uma entrada de servidor MCP.

Fronteira do caso de uso (mesmo papel que
`src/application/integrations/config_schemas.py` cumpre para
`user_integrations`): valida a FORMA de uma entrada antes de qualquer
persistência, replicando em tempo de escrita a mesma regra que
`src/agents/unified/mcp_client.py::build_connection` já aplica em tempo de
conexão — `command` obrigatório para `transport=stdio`, `url` obrigatório
para `transport=http` (REQ-001 do spec `user-mcp-server-store`). Pega o erro
na hora de salvar a configuração, não só quando o agente tentar conectar.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class McpServerEntryConfig(BaseModel):
    """Forma validada de uma entrada `mcpServers` — stdio ou http."""

    transport: Literal["stdio", "http"]
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_field_for_transport(self) -> McpServerEntryConfig:
        if self.transport == "stdio" and not self.command:
            raise ValueError("transporte 'stdio' exige o campo 'command'.")
        if self.transport == "http" and not self.url:
            raise ValueError("transporte 'http' exige o campo 'url'.")
        return self


__all__ = ["McpServerEntryConfig"]
