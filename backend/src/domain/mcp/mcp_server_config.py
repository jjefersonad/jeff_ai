"""Domínio de servidores MCP por usuário: entidade `McpServerConfig`.

PURO: zero import de framework — mesma convenção de `UserIntegration`
(`src/domain/integrations/user_integration.py`). Cifra/decifra de
`env`/`headers` é responsabilidade da camada de `infrastructure`; validação
de forma (campo obrigatório por `transport`) é responsabilidade da fronteira
de aplicação (`src/application/mcp/mcp_server_schema.py`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.domain.shared.errors import DomainError


@dataclass
class McpServerConfig:
    """Um servidor MCP declarado por um único `user_id`.

    Mapeia 1:1 com a linha de `user_mcp_servers`
    (`user-scoped-mcp-config-storage-task-db-1`). `transport` seleciona quais
    de `command`/`args` (stdio) ou `url` (http) são relevantes — nenhum dos
    dois é validado aqui; essa checagem é feita mais cedo, em
    `McpServerEntryConfig`, antes da entidade ser construída.
    """

    id: str
    user_id: str
    name: str
    transport: str
    command: str | None = None
    args: list[str] = field(default_factory=list)
    url: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        """Valida que os campos identificadores obrigatórios não estão vazios."""
        for attr_name in ("id", "user_id", "name", "transport"):
            value = getattr(self, attr_name)
            if not isinstance(value, str) or not value.strip():
                raise DomainError(
                    f"McpServerConfig.{attr_name} é obrigatório e não pode ser vazio."
                )
