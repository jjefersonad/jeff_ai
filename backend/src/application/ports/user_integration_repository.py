"""Port de repositório de credenciais de integração por usuário.

REQ-001 do spec `user-integration-credentials-store`. Abstrai a
persistência de `UserIntegration` (Postgres no adapter) do
restante da camada de aplicação. Implementações cifram/decifram os campos
sensíveis de `config` (REQ-002) — o port em si só conhece texto plano.
`get()` retorna `None` para entrada inexistente — NUNCA levanta exceção.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.integrations import UserIntegration


class UserIntegrationRepositoryPort(ABC):
    """Persiste `UserIntegration`, escopada ao `user_id` dono de cada entrada.

    Implementações devem ser idempotentes em `save()` e tolerantes a
    entrada inexistente em `get()` e `delete()`.
    """

    @abstractmethod
    async def save(self, integration: UserIntegration) -> None:
        """Cria ou atualiza a entrada persistida (id é a chave primária)."""
        raise NotImplementedError

    @abstractmethod
    async def get(self, integration_id: str) -> UserIntegration | None:
        """Retorna a entrada pelo `integration_id` ou `None` se não existir.

        Nunca levanta exceção para `integration_id` inexistente — o caller
        decide o que fazer (criar, falhar, retornar 404).
        """
        raise NotImplementedError

    @abstractmethod
    async def list_by_user(self, user_id: str) -> list[UserIntegration]:
        """Retorna as entradas cujo `user_id` corresponde (REQ-001)."""
        raise NotImplementedError

    @abstractmethod
    async def list_all(self) -> list[UserIntegration]:
        """Retorna TODAS as entradas, de todos os usuários (REQ-004).

        Uso restrito a callers `role=admin` — a própria porta não impõe essa
        checagem, ela é responsabilidade do use case (mesmo padrão de
        `ScheduledTaskRepositoryPort.list_all`).
        """
        raise NotImplementedError

    @abstractmethod
    async def delete(self, integration_id: str) -> None:
        """Remove a entrada. Tolerante a `integration_id` inexistente (no-op)."""
        raise NotImplementedError
