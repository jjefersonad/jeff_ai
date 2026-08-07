"""Port de repositório de servidores MCP por usuário.

REQ-001 do spec `user-mcp-server-store`. Abstrai a persistência de
`McpServerConfig` (Postgres no adapter) do restante da camada de aplicação —
mesmo padrão de `UserIntegrationRepositoryPort`. Implementações cifram/
decifram os valores sensíveis de `env`/`headers` (REQ-002) — o port em si só
conhece texto plano. `get()` retorna `None` para entrada inexistente — NUNCA
levanta exceção.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.mcp import McpServerConfig


class McpServerRepositoryPort(ABC):
    """Persiste `McpServerConfig`, escopado ao `user_id` dono de cada servidor.

    Implementações devem ser idempotentes em `save()` e tolerantes a entrada
    inexistente em `get()` e `delete()`.
    """

    @abstractmethod
    async def save(self, server: McpServerConfig) -> None:
        """Cria ou atualiza a entrada persistida (chave é `(user_id, name)`)."""
        raise NotImplementedError

    @abstractmethod
    async def get(self, user_id: str, name: str) -> McpServerConfig | None:
        """Retorna o servidor pelo par `(user_id, name)` ou `None` se não existir.

        Nunca levanta exceção para entrada inexistente — o caller decide o
        que fazer (criar, falhar, retornar 404).
        """
        raise NotImplementedError

    @abstractmethod
    async def list_by_user(self, user_id: str) -> list[McpServerConfig]:
        """Retorna os servidores cujo `user_id` corresponde (REQ-001)."""
        raise NotImplementedError

    @abstractmethod
    async def list_all(self) -> list[McpServerConfig]:
        """Retorna TODOS os servidores, de todos os usuários.

        Uso restrito a callers `role=admin` — a própria porta não impõe essa
        checagem, ela é responsabilidade do use case (mesmo padrão de
        `UserIntegrationRepositoryPort.list_all`).
        """
        raise NotImplementedError

    @abstractmethod
    async def delete(self, user_id: str, name: str) -> None:
        """Remove o servidor. Tolerante a entrada inexistente (no-op)."""
        raise NotImplementedError
