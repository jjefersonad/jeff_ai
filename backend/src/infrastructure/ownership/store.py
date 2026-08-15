"""Registro e checagem de ownership de arquivos gerados (`generated_files`).

`record_ownership` segue o mesmo padrão de
`src/infrastructure/attachments/store.py` — usa o pool compartilhado de
`src/infrastructure/auth/db.py`. `user_id` vem do `user_key` no `configurable`
do run (contextvar do LangGraph, stampado server-side em
`src/infrastructure/web/auth.py`).

`resolve_user_id` é o resolvedor canônico `user_key → user_id` (design
Decision 4 de `user-integration-credentials`): `web:<uuid>` retorna o uuid
direto; `telegram:<chat_id>` e `whatsapp:<phone_number>` consultam
`user_integrations` (`task store-2` / `whatsapp-evolution-channel-task
resolve-1`) por um vínculo ativo. Para Telegram, se não houver vínculo e
o `chat_id` for o allowlist legado (`TELEGRAM_AUTHORIZED_CHAT_ID`) com
`TELEGRAM_LEGACY_OWNER_USER_ID` setada, usa esse UUID como ponte de
memória/ownership (`fix-memory-access-user-identity`). Sem vínculo e
sem ponte, retorna `None`.

`is_authorized` (REQ-002 de `media-ownership-authorization`) é usada pelos
routers HTTP (`documents_router.py`, `images_router.py`) para decidir se o
usuário autenticado da requisição pode baixar um arquivo específico.
"""
from __future__ import annotations

import os

from langgraph.config import get_config

from src.infrastructure.auth.db import get_pool
from src.infrastructure.auth.users import User
from src.infrastructure.persistence.user_integrations_repository import (
    PostgresUserIntegrationRepository,
)

_WEB_USER_KEY_PREFIX = "web:"
_TELEGRAM_USER_KEY_PREFIX = "telegram:"
_WHATSAPP_USER_KEY_PREFIX = "whatsapp:"
_TELEGRAM_INTEGRATION_TYPE = "telegram"
_WHATSAPP_INTEGRATION_TYPE = "whatsapp_business"


async def resolve_user_id() -> str | None:
    """Resolve o `user_id` (UUID de `users.id`) do `user_key` do run atual."""
    configurable = get_config().get("configurable", {})
    user_key = configurable.get("user_key")
    if not user_key:
        return None
    if user_key.startswith(_WEB_USER_KEY_PREFIX):
        return user_key.removeprefix(_WEB_USER_KEY_PREFIX)
    if user_key.startswith(_TELEGRAM_USER_KEY_PREFIX):
        chat_id = user_key.removeprefix(_TELEGRAM_USER_KEY_PREFIX)
        return await resolve_telegram_user_id(chat_id)
    if user_key.startswith(_WHATSAPP_USER_KEY_PREFIX):
        phone_number = user_key.removeprefix(_WHATSAPP_USER_KEY_PREFIX)
        return await resolve_whatsapp_user_id(phone_number)
    return None


def _legacy_telegram_owner_user_id(chat_id: str) -> str | None:
    """Ponte allowlist legado → `users.id` para memória/ownership.

    Só aplica quando `chat_id` é exatamente `TELEGRAM_AUTHORIZED_CHAT_ID` e
    `TELEGRAM_LEGACY_OWNER_USER_ID` está setada (UUID do dono). Vínculo em
    `user_integrations` tem precedência — esta função só é consultada depois.
    """
    authorized_chat_id = os.environ.get("TELEGRAM_AUTHORIZED_CHAT_ID", "")
    legacy_owner = os.environ.get("TELEGRAM_LEGACY_OWNER_USER_ID", "").strip()
    if not chat_id or not authorized_chat_id or not legacy_owner:
        return None
    if chat_id != authorized_chat_id:
        return None
    return legacy_owner


async def resolve_telegram_user_id(chat_id: str) -> str | None:
    """Vínculo `chat_id → user_id` via `user_integrations`, com ponte legado.

    Resolvedor canônico reaproveitado também por
    `telegram/authorization.py` (task `channel-1`) para decidir a
    autorização de um `chat_id` fora do contexto de um run (sem
    `configurable` do LangGraph disponível ainda) — é por isso que a
    função recebe `chat_id` diretamente em vez de ler `get_config()`.

    `config` é cifrado em repouso (task `store-2`), então não dá para
    filtrar por `chat_id` em SQL — decifra cada entrada `telegram` (via o
    repositório, que já decifra) e compara em Python. Sem vínculo, cai na
    ponte `TELEGRAM_LEGACY_OWNER_USER_ID` se o chat for o da allowlist.
    """
    repository = PostgresUserIntegrationRepository(os.environ["POSTGRES_URI"])
    for integration in await repository.list_all():
        if (
            integration.integration_type == _TELEGRAM_INTEGRATION_TYPE
            and integration.config.get("chat_id") == chat_id
        ):
            return integration.user_id
    return _legacy_telegram_owner_user_id(chat_id)


async def resolve_whatsapp_user_id(phone_number: str) -> str | None:
    """Vínculo `phone_number → user_id` via `user_integrations`.

    Mesmo padrão de `resolve_telegram_user_id`: `config` é cifrado em
    repouso, então decifra cada entrada `whatsapp_business` (via o
    repositório, que já decifra) e compara em Python.
    """
    repository = PostgresUserIntegrationRepository(os.environ["POSTGRES_URI"])
    for integration in await repository.list_all():
        if (
            integration.integration_type == _WHATSAPP_INTEGRATION_TYPE
            and integration.config.get("phone_number") == phone_number
        ):
            return integration.user_id
    return None


async def record_ownership(
    *,
    kind: str,
    filename: str,
    user_id: str | None = None,
) -> None:
    """Grava o dono do arquivo recém-gerado (`kind`/`filename`) em `generated_files`.

    Sem `user_id` (argumento ou `resolve_user_id()`), falha fechado — não é
    mais no-op silencioso (session-file-sandbox D8 / media REQ-007). Erros do
    Postgres também propagam: a tool geradora trata exceção como falha na
    geração, sem deixar arquivo "sem dono" em silêncio.
    """
    from src.infrastructure.ownership.session_writers import MissingUserIdentityError

    owner = user_id if user_id is not None else await resolve_user_id()
    if owner is None:
        raise MissingUserIdentityError(
            "user_id is required to record ownership (no session identity)"
        )

    pool = get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO generated_files (user_id, kind, filename) "
            "VALUES (%s, %s, %s) ON CONFLICT (kind, filename) DO NOTHING",
            (owner, kind, filename),
        )


async def list_owned_filenames(*, kind: str, user_id: str) -> frozenset[str]:
    """Nomes de arquivos (`kind`) gravados em `generated_files` para `user_id`.

    Usada pelas listagens (REQ-003 / session-file-sandbox D7) para montar a
    lista a partir do DB + árvore `files/<user_id>/…` — não a partir de um
    diretório global compartilhado.
    """
    pool = get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT filename FROM generated_files WHERE kind = %s AND user_id = %s",
            (kind, user_id),
        )
        rows = await cur.fetchall()
    return frozenset(row[0] for row in rows)


async def get_file_owner(*, kind: str, filename: str) -> str | None:
    """Retorna o `user_id` dono de `(kind, filename)` em `generated_files`, ou None.

    Usado pelos handlers HTTP para derivar o path físico
    `files/<owner>/{docs|images|attachment}/<filename>` (D13) sem coluna
    `storage_path`.
    """
    pool = get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT user_id FROM generated_files WHERE kind = %s AND filename = %s",
            (kind, filename),
        )
        row = await cur.fetchone()
    return str(row[0]) if row is not None else None


async def is_authorized(*, kind: str, filename: str, user: User) -> bool:
    """REQ-002: `user` pode baixar `(kind, filename)`?

    `role admin` sempre autorizado, sem consultar o banco. Demais usuários só
    se forem o `user_id` gravado em `generated_files` para esse arquivo — sem
    linha correspondente (arquivo órfão em disco), o acesso é negado
    (fail-closed), mesmo para quem gerou outros arquivos do mesmo `kind`.
    """
    if user.role == "admin":
        return True

    pool = get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT user_id FROM generated_files WHERE kind = %s AND filename = %s",
            (kind, filename),
        )
        row = await cur.fetchone()

    return row is not None and str(row[0]) == user.id


async def resolve_role_for_user_key(user_key: str | None) -> str:
    """Resolve `admin`/`user` a partir de um `user_key` explícito (DirectRunner).

    Fail-closed: chave ausente, `unknown`, canal sem vínculo ou user
    inexistente ⇒ `\"user\"` (session-file-sandbox REQ-001 / D2).
    """
    from src.infrastructure.auth.users import get_user_by_id

    if not user_key or user_key == "unknown":
        return "user"

    user_id: str | None = None
    if user_key.startswith(_WEB_USER_KEY_PREFIX):
        user_id = user_key.removeprefix(_WEB_USER_KEY_PREFIX)
    elif user_key.startswith(_TELEGRAM_USER_KEY_PREFIX):
        chat_id = user_key.removeprefix(_TELEGRAM_USER_KEY_PREFIX)
        user_id = await resolve_telegram_user_id(chat_id)
    elif user_key.startswith(_WHATSAPP_USER_KEY_PREFIX):
        phone_number = user_key.removeprefix(_WHATSAPP_USER_KEY_PREFIX)
        user_id = await resolve_whatsapp_user_id(phone_number)

    if not user_id:
        return "user"

    user = await get_user_by_id(user_id)
    if user is None:
        return "user"
    return "admin" if user.role == "admin" else "user"
