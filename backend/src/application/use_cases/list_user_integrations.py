"""Caso de uso: listar credenciais de integração de usuário.

Cobre REQ-001 (escopo por dono) e REQ-004 (visão admin sem decifrar
segredo alheio) do spec `user-integration-credentials-store`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)


@dataclass(frozen=True)
class UserIntegrationSummary:
    """Projeção de `UserIntegration` para listagem — metadados sempre visíveis.

    `config` só é preenchido quando a entrada pertence ao chamador; para
    entradas de outros usuários (visão admin, REQ-004) vem `None` — nunca o
    valor decifrado.
    """

    id: str
    user_id: str
    integration_type: str
    created_at: datetime
    updated_at: datetime
    config: dict[str, object] | None


class ListUserIntegrations:
    """Lista credenciais de integração escopadas ao chamador (REQ-001/REQ-004).

    Depende apenas da porta de repositório; não conhece Postgres nem
    qualquer adapter concreto.
    """

    def __init__(self, *, repository: UserIntegrationRepositoryPort) -> None:
        """Recebe a porta de repositório por injeção de dependência."""
        self._repository = repository

    async def execute(
        self,
        *,
        caller_user_id: str,
        is_admin: bool,
    ) -> list[UserIntegrationSummary]:
        """Retorna as entradas visíveis ao chamador.

        Args:
            caller_user_id: `user_id` do chamador autenticado.
            is_admin: True se o chamador tem `role=admin` (bypass de
                ownership para a LISTA, nunca para o `config` decifrado).

        Returns:
            Lista de `UserIntegrationSummary`. Não-admin: só as próprias
            entradas, sempre com `config`. Admin: entradas de todos os
            usuários, mas `config` só nas que o próprio admin possui
            (REQ-004) — as demais vêm com `config=None`.
        """
        integrations = (
            await self._repository.list_all()
            if is_admin
            else await self._repository.list_by_user(caller_user_id)
        )
        return [
            UserIntegrationSummary(
                id=integration.id,
                user_id=integration.user_id,
                integration_type=integration.integration_type,
                created_at=integration.created_at,
                updated_at=integration.updated_at,
                config=(
                    integration.config
                    if integration.user_id == caller_user_id
                    else None
                ),
            )
            for integration in integrations
        ]
