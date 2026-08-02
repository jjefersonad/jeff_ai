"""Rota admin de agregação de uso de tokens (`GET /api/usage`).

Somente `role=admin` (via `require_admin`). Consulta somente leitura sobre
`UsageRepository.aggregate` — filtros opcionais de período, provedor, modelo
e `user_key`.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from src.infrastructure.auth.dependencies import require_admin
from src.infrastructure.auth.users import User
from src.infrastructure.usage.repository import UsageRepository

router = APIRouter()


def _usage_repository() -> UsageRepository:
    """Constrói o repositório a partir de `POSTGRES_URI`."""
    return UsageRepository(os.environ["POSTGRES_URI"])


@router.get("/api/usage")
async def get_usage(
    _admin: User = Depends(require_admin),
    user_key: str | None = Query(default=None),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    provider: str | None = Query(default=None),
    model: str | None = Query(default=None),
    repo: UsageRepository = Depends(_usage_repository),
) -> dict[str, Any]:
    """Agrega tokens persistidos. Admin-only; sem side effects de escrita."""
    return repo.aggregate(
        user_key=user_key,
        from_ts=from_,
        to_ts=to,
        provider=provider,
        model=model,
    )
