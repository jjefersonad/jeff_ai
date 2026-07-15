"""Rotas HTTP públicas de autenticação (`/public/login`, `/public/logout`).

Cria/revoga sessões server-side (task-rest-1, ver design da mudança
`autenticacao-jwt-rotas-protegidas`): login valida credenciais via bcrypt
(`security.verify_password`) contra a tabela `users` (`users.get_user_by_username`)
e entrega um cookie de sessão opaco (`sessions.create_session`); logout revoga
a sessão imediatamente (`sessions.revoke_session`) e limpa o cookie.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from fastapi.requests import Request
from pydantic import BaseModel

from src.infrastructure.auth.security import verify_password
from src.infrastructure.auth.sessions import (
    SESSION_COOKIE_NAME,
    create_session,
    revoke_session,
)
from src.infrastructure.auth.users import get_user_by_username

router = APIRouter()


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
        httponly=True,
        secure=True,
        samesite="strict",
    )
    return {"username": user.username, "role": user.role}


@router.post("/public/logout")
async def logout(request: Request, response: Response) -> dict[str, str]:
    """Revoga a sessão do cookie (se houver) e limpa o cookie no cliente."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        await revoke_session(token)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"detail": "logged out"}
