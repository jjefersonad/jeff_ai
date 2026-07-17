"""Handler de autenticação nativo do LangGraph (`auth.path` em `langgraph.json`).

Protege as rotas nativas do backend LangGraph (`/threads`, `/runs`,
`/assistants`, `/crons`, `/store`) para os 4 graph IDs de `langgraph.json`
(`unified`, `agent`, `sdd_agent`, `assistant` — todos compilam o mesmo grafo
`unified`, ver Known Debt do CLAUDE.md). Usa o MESMO núcleo de resolução de
sessão que `dependencies.require_auth` (`session_resolver.resolve_session_user`)
— REQ-003 de `langgraph-native-auth-middleware` exige que o usuário resolvido
seja o mesmo modelo de sessão (mesma tabela `sessions`/`users`) nos dois
pontos de entrada.

`/public/*` é liberado explicitamente (via `resolve_session_user` devolvendo
`None` para paths públicos) — necessário para o próprio `/public/login` não
exigir sessão.

CONFIRMADO EMPIRICAMENTE (2026-07-15, `langgraph dev` real + curl): este
handler NÃO cobre as rotas de `http.app` (`webapp.py`) — `GET /api/images`
sem cookie retornou 200 quando a dependency `require_auth` foi
temporariamente removida de `webapp.py`, enquanto `/threads` continuou
retornando 401 por este handler. Ou seja, os dois mecanismos são
INDEPENDENTES e ambos necessários: este cobre as rotas nativas do LangGraph
(`/threads`, `/runs`, `/assistants`, `/crons`), `require_auth`
(`dependencies.py`, task-rest-3) cobre as rotas de `http.app`. Isso resolve
a Open Question do design ("`@auth.authenticate` cobre rotas de `http.app`?")
com resposta definitiva: não.

Nenhum `@auth.on` é registrado: sem handler de autorização por recurso, o
comportamento default do LangGraph é aceitar a requisição após a autenticação
bem-sucedida (ver docstring de `Auth._On`).
"""

from __future__ import annotations

from langgraph_sdk import Auth
from starlette.requests import Request

from src.infrastructure.auth.session_resolver import (
    SessionAuthError,
    resolve_session_user,
)

auth = Auth()


@auth.authenticate
async def authenticate(request: Request) -> Auth.types.MinimalUserDict:
    """Valida a sessão do cookie; libera `/public/*` sem exigir uma."""
    try:
        user = await resolve_session_user(request)
    except SessionAuthError as exc:
        raise Auth.exceptions.HTTPException(status_code=401, detail="Unauthorized") from exc

    if user is None:
        # Path público (ex.: `/public/login`) — sem sessão exigida.
        return {"identity": "public", "is_authenticated": False, "permissions": []}

    return {
        "identity": user.id,
        "display_name": user.username,
        "permissions": [user.role],
        "is_authenticated": True,
    }
