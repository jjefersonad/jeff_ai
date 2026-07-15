"""FastAPI dependencies que impõem sessão autenticada nas rotas REST.

`require_auth` é registrada como dependency global do app
(`FastAPI(dependencies=[Depends(require_auth)])` em `webapp.py`, task-rest-3)
e cobre TODAS as rotas por padrão — incluindo as de `images_router`/
`documents_router`, que antes eram públicas. Rotas cujo path corresponda a
`PUBLIC_PATHS` (env var, lista separada por vírgula; default `/public/`) são
liberadas DENTRO da própria dependency: como ela é global, isso resolve o
"ovo e galinha" de exigir sessão para acessar o próprio `/public/login`.

`require_admin` compõe sobre `require_auth` e adiciona a checagem de
`role == 'admin'` (403 caso contrário) — usado por endpoints restritos a
administradores (ex.: cadastro de usuário, entregue pela change
`user-management`).

A resolução de sessão em si (cookie → `sessions` → `users`, e a checagem de
`PUBLIC_PATHS`) vive em `session_resolver.py`, compartilhada com o handler
nativo do LangGraph (`web/auth.py`, task-langgraph-auth-1) — ver REQ-003 de
`langgraph-native-auth-middleware`.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from src.infrastructure.auth.session_resolver import (
    SessionAuthError,
    resolve_session_user,
)
from src.infrastructure.auth.users import User


async def require_auth(request: Request) -> User | None:
    """Exige sessão válida, exceto para paths em `PUBLIC_PATHS`.

    Devolve o usuário autenticado (com `role`), ou `None` se o path é
    público. 401 se o cookie de sessão estiver ausente, for desconhecido,
    expirado, ou apontar para um usuário removido/inativo.
    """
    try:
        return await resolve_session_user(request)
    except SessionAuthError as exc:
        raise HTTPException(status_code=401, detail="Unauthorized") from exc


async def require_admin(user: User | None = Depends(require_auth)) -> User:
    """Exige que o usuário autenticado tenha `role == 'admin'` (403 caso contrário)."""
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return user
