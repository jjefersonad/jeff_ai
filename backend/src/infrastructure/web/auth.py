"""Handler de autenticação nativo do LangGraph (`auth.path` em `langgraph.json`).

Em Docker/produção a imagem `langgraph-api` NÃO lê `auth.path` do json em
runtime — só a env `LANGGRAPH_AUTH` (mesmo padrão de `LANGGRAPH_HTTP`). Sem
ela, `LANGGRAPH_AUTH_TYPE` fica `noop` e estes handlers nunca rodam
(`fix-thread-list-user-isolation`). Compose deve exportar:
`LANGGRAPH_AUTH='{"path": "./src/infrastructure/web/auth.py:auth"}'`.

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

Um único handler `@auth.on` (sem qualificador de recurso) aplica autorização
por dono a `threads`/`runs`/`crons` — os únicos recursos nativos escopados
neste change (ver `user-data-isolation-design`, decisão "Ownership de
threads/runs/crons via @auth.on global + metadata.owner"). `assistants` e o
`store` nativo ficam fora de escopo (handler devolve filtro vazio para eles) —
ver Open Questions do design.

`@auth.on.threads.create_run` carimba `configurable.user_key = web:<identity>`
e `configurable.role` (`user`/`admin`) a partir da sessão (nunca do body do
frontend) — metering (`track-user-token-usage`) + sandbox por role
(`session-file-sandbox`).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langgraph_sdk import Auth
from starlette.requests import Request

from src.infrastructure.auth.session_resolver import (
    SessionAuthError,
    resolve_session_user,
)
from src.infrastructure.usage.user_key import web_user_key

auth = Auth()


def role_from_permissions(permissions: Sequence[str] | None) -> str:
    """Deriva `user`/`admin` de `permissions` (fail-closed: default `user`)."""
    if permissions and "admin" in permissions:
        return "admin"
    return "user"


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


_OWNER_SCOPED_RESOURCES = ("threads", "runs", "crons")


def _stamp_web_run_identity(
    value: dict[str, Any],
    identity: str,
    *,
    permissions: Sequence[str] | None = None,
) -> str:
    """Carimba `configurable.user_key` e `configurable.role` no create_run.

    Sempre sobrescreve valores enviados pelo cliente — o frontend nunca é
    fonte de verdade (track-user-token-usage / session-file-sandbox REQ-001).
    """
    key = web_user_key(identity)
    role = role_from_permissions(permissions)
    metadata = value.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["owner"] = identity

    kwargs = value.setdefault("kwargs", {})
    if not isinstance(kwargs, dict):
        kwargs = {}
        value["kwargs"] = kwargs

    config = kwargs.setdefault("config", {})
    if not isinstance(config, dict):
        config = {}
        kwargs["config"] = config

    configurable = config.setdefault("configurable", {})
    if not isinstance(configurable, dict):
        configurable = {}
        config["configurable"] = configurable

    configurable["user_key"] = key
    configurable["role"] = role
    return key


# Alias preservado para imports/testes legados que ainda citam o nome antigo.
_stamp_web_user_key = _stamp_web_run_identity


@auth.on.threads.create_run
async def stamp_user_key_on_run_create(
    ctx: Auth.types.AuthContext,
    value: dict,
) -> Auth.types.FilterType:
    """Carimba `user_key` + `role` server-side ao criar um run web.

    Mais específico que `@auth.on` — toma precedência em `create_run`.
    Replica o filtro por `owner` (e bypass de admin) do handler global, e
    adicionalmente injeta `configurable.user_key` / `configurable.role`,
    sobrescrevendo qualquer valor do cliente.
    """
    identity = ctx.user.identity
    _stamp_web_run_identity(value, identity, permissions=ctx.user.permissions)

    if "admin" in ctx.user.permissions:
        return {}
    return {"owner": identity}


@auth.on
async def authorize_by_owner(
    ctx: Auth.types.AuthContext, value: dict
) -> Auth.types.FilterType:
    """Escopa `threads`/`runs`/`crons` por `metadata.owner`; `admin` vê tudo.

    Handler global (sem qualificador de resource) — chamado também para
    `assistants`/`store`, que ficam fora de escopo deste change e recebem
    filtro vazio (nem stamping, nem restrição). `role admin` é o único sinal
    de bypass (REQ-009 de `backend-session-auth`), lido de
    `ctx.user.permissions` — o mesmo valor que `authenticate()` populou a
    partir de `user.role`, sem reimplementar a resolução de sessão (REQ-008).

    `create_run` é tratado por `stamp_user_key_on_run_create` (mais específico);
    este handler não roda nesse caminho.
    """
    if "admin" in ctx.user.permissions or ctx.resource not in _OWNER_SCOPED_RESOURCES:
        return {}

    if ctx.action == "create":
        metadata = value.setdefault("metadata", {})
        metadata["owner"] = ctx.user.identity

    return {"owner": ctx.user.identity}
