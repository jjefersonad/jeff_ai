"""Testes de `authorize_by_owner` (`src/infrastructure/web/auth.py`).

Cobre `thread-ownership-authorization` (change `user-data-isolation`,
task-threads-2):
- REQ-002: `threads.search` filtra por `metadata.owner` para role `user`;
  sem filtro para `admin`.
- REQ-003: `get`/`update`/`delete` sobre `threads` de outro usuário retornam
  o mesmo filtro por owner usado em REQ-002 (é o filtro que a SDK do
  LangGraph usa para negar/404 acesso cross-user); `admin` não é filtrado.
- REQ-004: mesma regra aplicada a `crons`.
- `assistants`/`store` NÃO são escopados por este handler — sempre `{}`,
  independente de role.

CONFIRMADO EMPIRICAMENTE (2026-07-29, `jeff_ia_backend` real via docker compose,
Postgres real com 55 threads legadas — todas sem `metadata.owner` — + curl,
mesmo protocolo diferencial usado em `test_langgraph_auth.py`; task-threads-3):
regra "thread/cron sem `metadata.owner` == pertence ao admin de bootstrap" não
exige nenhuma checagem extra no código — decorre diretamente do filtro
estrito `{"owner": identity}` combinado com o bypass total de `admin`. Dois
usuários descartáveis foram criados via SQL direto (role `user` e role
`admin`), logados via `POST /public/login`, testados contra uma thread real
pré-existente sem owner (`019f845c-2e57-7df2-b1f5-478e1188e895`), e removidos
ao final (sessões revogadas + linhas deletadas — nenhum dado real alterado):
- `GET /threads/<id>` como `user`: `404 {"detail":"thread ... not found"}`
  (não confirma nem nega existência a quem não tem acesso — REQ-003).
- `GET /threads/<id>` como `admin`: `200`, corpo sem `metadata.owner`
  (prova de que a thread é de fato legada/sem dono).
- `POST /threads/search` como `user`: thread legada ausente dos resultados.
- `POST /threads/search` como `admin`: thread legada presente nos resultados.
`/crons` não está ativo neste deployment (`404 Not Found` na rota) — a
paridade de regra para `crons` (REQ-004) fica coberta pelos testes
automatizados abaixo, que exercitam o mesmo branch de código
(`_OWNER_SCOPED_RESOURCES`) usado por `threads`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import pytest
from langgraph_sdk.auth import types as auth_types

from src.infrastructure.web.auth import authorize_by_owner


@dataclass
class _FakeUser:
    identity: str
    permissions: Sequence[str] = ("user",)
    is_authenticated: bool = True
    display_name: str = "test"


def _auth_ctx(
    identity: str,
    *,
    resource: str,
    action: str,
    permissions: Sequence[str] = ("user",),
) -> auth_types.AuthContext:
    user = _FakeUser(identity=identity, permissions=permissions)
    return auth_types.AuthContext(
        user=user,  # type: ignore[arg-type]
        permissions=list(permissions),
        resource=resource,  # type: ignore[arg-type]
        action=action,  # type: ignore[arg-type]
    )


# --- REQ-002: filtragem de listagem por owner --------------------------------


async def test_threads_search_filters_by_owner_for_user_role() -> None:
    ctx = _auth_ctx("user-1", resource="threads", action="search")

    result = await authorize_by_owner(ctx, {})

    assert result == {"owner": "user-1"}


async def test_threads_search_returns_all_for_admin() -> None:
    ctx = _auth_ctx("admin-1", resource="threads", action="search", permissions=("admin",))

    result = await authorize_by_owner(ctx, {})

    assert result == {}


# --- REQ-003: bloqueio de acesso direto a thread alheia -----------------------


@pytest.mark.parametrize("action", ["read", "update", "delete"])
async def test_threads_read_update_delete_scoped_by_owner_for_user_role(action: str) -> None:
    ctx = _auth_ctx("user-1", resource="threads", action=action)

    result = await authorize_by_owner(ctx, {})

    assert result == {"owner": "user-1"}


@pytest.mark.parametrize("action", ["read", "update", "delete"])
async def test_threads_read_update_delete_unscoped_for_admin(action: str) -> None:
    ctx = _auth_ctx("admin-1", resource="threads", action=action, permissions=("admin",))

    result = await authorize_by_owner(ctx, {})

    assert result == {}


# --- REQ-004: mesma filtragem aplicada a crons --------------------------------


async def test_crons_search_filters_by_owner_for_user_role() -> None:
    ctx = _auth_ctx("user-1", resource="crons", action="search")

    result = await authorize_by_owner(ctx, {})

    assert result == {"owner": "user-1"}


@pytest.mark.parametrize("action", ["update", "delete"])
async def test_crons_update_delete_scoped_by_owner_for_user_role(action: str) -> None:
    ctx = _auth_ctx("user-1", resource="crons", action=action)

    result = await authorize_by_owner(ctx, {})

    assert result == {"owner": "user-1"}


async def test_crons_search_returns_all_for_admin() -> None:
    ctx = _auth_ctx("admin-1", resource="crons", action="search", permissions=("admin",))

    result = await authorize_by_owner(ctx, {})

    assert result == {}


# --- assistants/store ficam fora de escopo deste handler ---------------------


@pytest.mark.parametrize("resource", ["assistants", "store"])
@pytest.mark.parametrize("role", [("user",), ("admin",)])
async def test_out_of_scope_resources_are_never_filtered(
    resource: str, role: Sequence[str]
) -> None:
    ctx = _auth_ctx("user-1", resource=resource, action="search", permissions=role)

    result = await authorize_by_owner(ctx, {})

    assert result == {}
