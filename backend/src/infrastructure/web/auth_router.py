"""Rotas HTTP públicas de autenticação (`/public/login`, `/public/logout`)
e o probe de sessão `GET /api/me`.

Cria/revoga sessões server-side (task-rest-1, ver design da mudança
`autenticacao-jwt-rotas-protegidas`): login valida credenciais via bcrypt
(`security.verify_password`) contra a tabela `users` (`users.get_user_by_username`)
e entrega um cookie de sessão opaco (`sessions.create_session`); logout revoga
a sessão imediatamente (`sessions.revoke_session`) e limpa o cookie.

`GET /api/me` (auth-session-rehydration) devolve `{id, username, role}` a partir
do cookie de sessão — usado pelo `AuthProvider` no mount para rehidratar o
estado React após hard reload (sem isso, páginas admin como `/admin/users`
ficam sem `user.role` e nunca disparam o fetch). O `id` (`users.id`) isola o
cache SWR de threads entre sessões (`fix-thread-list-user-isolation`).
"""

from __future__ import annotations

import os
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.requests import Request
from pydantic import BaseModel

from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.security import verify_password
from src.infrastructure.auth.sessions import (
    SESSION_COOKIE_NAME,
    create_session,
    revoke_session,
)
from src.infrastructure.auth.users import User, get_user_by_username

router = APIRouter()

# Front em jeff.X e API em jeff-api.X: sem Domain=.X o cookie fica só no host
# da API e o middleware do Next (no host do front) não vê a sessão → loop em
# /public/login. Em localhost deixe COOKIE_DOMAIN vazio.
_SameSite = Literal["strict", "lax", "none"]


def _cookie_kwargs() -> dict[str, Any]:
    raw_domain = (os.getenv("COOKIE_DOMAIN") or "").strip()
    raw_samesite = (os.getenv("COOKIE_SAMESITE") or "lax").strip().lower()
    samesite: _SameSite
    if raw_samesite in ("strict", "lax", "none"):
        samesite = raw_samesite  # type: ignore[assignment]
    else:
        samesite = "lax"
    kwargs: dict[str, Any] = {
        "httponly": True,
        "secure": True,
        "samesite": samesite,
        "path": "/",
    }
    if raw_domain:
        kwargs["domain"] = raw_domain
    return kwargs


class LoginRequest(BaseModel):
    """Corpo de `POST /public/login`."""

    username: str
    password: str


@router.post("/public/login")
async def login(payload: LoginRequest, response: Response) -> dict[str, str]:
    """Valida credenciais e, se corretas, cria uma sessão e seta o cookie.

    Credenciais inválidas (username desconhecido, usuário inativo ou senha
    incorreta) retornam 401 genérico — nunca indicam qual campo está errado,
    e nenhuma sessão é criada.
    """
    user = await get_user_by_username(payload.username)
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = await create_session(user.id)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        **_cookie_kwargs(),
    )
    return {"id": user.id, "username": user.username, "role": user.role}


@router.post("/public/logout")
async def logout(request: Request, response: Response) -> dict[str, str]:
    """Revoga a sessão do cookie (se houver) e limpa o cookie no cliente."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        await revoke_session(token)
    response.delete_cookie(SESSION_COOKIE_NAME, **_cookie_kwargs())
    return {"detail": "logged out"}


@router.get("/api/me")
async def me(user: User | None = Depends(require_auth)) -> dict[str, str]:
    """Devolve o usuário da sessão corrente (`id` + `username` + `role`).

    401 quando não há cookie/sessão válida — o frontend trata isso como
    "não autenticado" sem redirecionar (probe de rehidratação).
    """
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"id": user.id, "username": user.username, "role": user.role}
