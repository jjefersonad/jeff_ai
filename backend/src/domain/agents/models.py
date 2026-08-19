"""Domínio `agents`: entidade `AgentProfile`.

PURO: zero import de framework. Um `AgentProfile` representa um agente
customizado por usuário — identifica o dono (`user_id`), tem `slug`
único-por-usuário, prompt de sistema, allowlists opcionais de
skills/tools/MCP, e `tier` (1..4) que mapeia ao regime de aprovação do
`tier_config.py` da camada de composição.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.domain.shared.errors import DomainError

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


@dataclass
class AgentProfile:
    """Perfil de agente customizado pertencente a um único `user_id`.

    `slug` é único por `user_id` (constraint de unicidade no DB). O
    par `(user_id, slug)` é a chave natural da entidade.
    """

    id: str
    user_id: str
    name: str
    slug: str
    system_prompt: str
    skills_allowlist: list[str] | None = None
    tools_allowlist: list[str] | None = None
    mcp_allowlist: list[str] | None = None
    tier: int = 1
    model_override: str | None = None
    is_active: bool = True
    archived_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        """Valida identificadores, `tier` (1..4) e `mcp_allowlist`."""
        for attr_name in ("id", "user_id", "name", "slug"):
            value = getattr(self, attr_name)
            if not isinstance(value, str) or not value.strip():
                raise DomainError(
                    f"AgentProfile.{attr_name} é obrigatório e não pode ser vazio."
                )
        if self.mcp_allowlist is not None and (
            not isinstance(self.mcp_allowlist, list)
            or not all(isinstance(item, str) for item in self.mcp_allowlist)
        ):
            raise DomainError(
                "AgentProfile.mcp_allowlist deve ser lista de strings ou None."
            )
        if not isinstance(self.tier, int) or not 1 <= self.tier <= 4:
            raise DomainError("AgentProfile.tier deve estar entre 1 e 4.")

    @staticmethod
    def validate_slug_format(slug: str) -> None:
        """Levanta `DomainError` se `slug` não estiver em kebab-case canônico.

        Formato aceito: `^[a-z0-9]+(-[a-z0-9]+)*$` — segmentos
        `[a-z0-9]+` unidos por hífen único; sem hífen inicial, final ou
        duplicado; sem underscores, espaços, letras maiúsculas.
        """
        if not isinstance(slug, str) or not _SLUG_PATTERN.match(slug):
            raise DomainError(
                "AgentProfile.slug deve ser kebab-case (ex.: 'coder-agent')."
            )
