"""Domínio de integrações de usuário: entidade `UserIntegration`.

PURO: zero import de framework. `config` guarda os dados específicos do
`integration_type` em texto plano — cifra/decifra é responsabilidade da
camada de `infrastructure` (design Decision 2 de
`user-integration-credentials`), nunca do domínio ou do caso de uso.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.domain.shared.errors import DomainError


@dataclass
class UserIntegration:
    """Uma credencial de integração pertencente a um único `user_id`.

    `integration_type` seleciona o schema de validação de `config`
    (`src/application/integrations/config_schemas.py`) — nenhum dos dois
    campos aqui impõe formato, para permitir novos tipos sem migração
    (REQ-003 do spec `user-integration-credentials-store`).
    """

    id: str
    user_id: str
    integration_type: str
    config: dict[str, object]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        """Valida que os campos identificadores obrigatórios não estão vazios."""
        for attr_name in ("id", "user_id", "integration_type"):
            value = getattr(self, attr_name)
            if not isinstance(value, str) or not value.strip():
                raise DomainError(
                    f"UserIntegration.{attr_name} é obrigatório e não pode ser vazio."
                )
