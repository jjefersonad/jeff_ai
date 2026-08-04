"""API administrativa de usuários (`/admin/users`, change `user-management`).

Router montado em `webapp.py`, `dependencies=[Depends(require_admin)]` no
nível do router — só este router exige `role=admin`; o restante do app
continua sob o `require_auth` global já existente (design Decision "Endpoints
REST sob `/admin/users`").

`UserPublic` lista os campos permitidos explicitamente — nunca serializa o
dataclass `User` inteiro, que inclui `password_hash` (REQ-001 do spec
`user-management-api`).

`POST /admin/users` (task-api-2): `CreateUserRequest.password` tem
`min_length=8` (REQ-002) — Pydantic rejeita com 422 antes do handler ser
chamado, então uma senha curta nunca chega a `get_password_hash`/`create_user`.

`PATCH /admin/users/{id}` (task-api-3): atualiza `role`/`is_active` via
`update_user`, que já embute o guarda-corpo de auto-lockout
(`SelfLockoutError`/`LastAdminError`, `task-core-3`). `patch_user`
(task-api-4) traduz os dois pra HTTP 409 — REQ-004.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.infrastructure.auth.dependencies import require_admin
from src.infrastructure.auth.security import get_password_hash
from src.infrastructure.auth.users import (
    LastAdminError,
    SelfLockoutError,
    User,
    create_user,
    list_users,
    update_user,
)

router = APIRouter(prefix="/admin", tags=["admin-users"], dependencies=[Depends(require_admin)])


class UserPublic(BaseModel):
    """Forma pública de `User` — sem `password_hash`."""

    id: str
    username: str
    role: str
    is_active: bool
    created_at: datetime


class UsersListResponse(BaseModel):
    """Corpo de resposta de `GET /admin/users`."""

    users: list[UserPublic]


class CreateUserRequest(BaseModel):
    """Corpo de `POST /admin/users`. `password` nunca é persistida — vira hash antes do `create_user`."""

    username: str
    password: str = Field(min_length=8)
    role: str = "user"


class PatchUserRequest(BaseModel):
    """Corpo de `PATCH /admin/users/{id}`. Campos omitidos mantêm o valor atual."""

    role: str | None = None
    is_active: bool | None = None


def _to_public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.get("/users")
async def get_users() -> UsersListResponse:
    """Lista todos os usuários (incluindo inativos), sem `password_hash`."""
    users = await list_users()
    return UsersListResponse(users=[_to_public(u) for u in users])


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def post_user(body: CreateUserRequest) -> UserPublic:
    """Cria um usuário com senha em hash bcrypt. Nunca aceita `password_hash` já pronto."""
    password_hash = get_password_hash(body.password)
    user = await create_user(username=body.username, password_hash=password_hash, role=body.role)
    return _to_public(user)


@router.patch("/users/{user_id}")
async def patch_user(
    user_id: str, body: PatchUserRequest, admin: User = Depends(require_admin)
) -> UserPublic:
    """Atualiza `role`/`is_active` de um usuário. Campos omitidos mantêm o valor atual.

    Guarda-corpo de auto-lockout (`SelfLockoutError`/`LastAdminError`,
    `task-core-3`) vira 409 aqui — task-api-4, REQ-004.
    """
    try:
        user = await update_user(
            user_id, role=body.role, is_active=body.is_active, caller_id=admin.id
        )
    except (SelfLockoutError, LastAdminError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _to_public(user)
