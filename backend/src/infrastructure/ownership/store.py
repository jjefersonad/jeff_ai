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
resolve-1`) por um vínculo ativo, e retornam `None` sem vínculo (mesmo
comportamento "zero servidores" de antes, agora estendido ao Telegram e
ao WhatsApp).

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


async def resolve_telegram_user_id(chat_id: str) -> str | None:
    """Vínculo `chat_id → user_id` via `user_integrations`.

    Resolvedor canônico reaproveitado também por
    `telegram/authorization.py` (task `channel-1`) para decidir a
    autorização de um `chat_id` fora do contexto de um run (sem
    `configurable` do LangGraph disponível ainda) — é por isso que a
    função recebe `chat_id` diretamente em vez de ler `get_config()`.

    `config` é cifrado em repouso (task `store-2`), então não dá para
    filtrar por `chat_id` em SQL — decifra cada entrada `telegram` (via o
    repositório, que já decifra) e compara em Python.
    """
    repository = PostgresUserIntegrationRepository(os.environ["POSTGRES_URI"])
    for integration in await repository.list_all():
        if (
            integration.integration_type == _TELEGRAM_INTEGRATION_TYPE
            and integration.config.get("chat_id") == chat_id
        ):
            return integration.user_id
    return None


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


async def record_ownership(*, kind: str, filename: str) -> None:
    """Grava o dono do arquivo recém-gerado (`kind`/`filename`) em `generated_files`.

    Sem `user_id` resolvível (`resolve_user_id()` retornou `None`), a chamada
    é um no-op. Erros do Postgres SÃO propagados (fail-closed): a tool
    geradora deve tratar exceção como falha na geração, não deixando o
    arquivo "sem dono" em silêncio.
    """
    user_id = await resolve_user_id()
    if user_id is None:
        return

    pool = get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO generated_files (user_id, kind, filename) "
            "VALUES (%s, %s, %s) ON CONFLICT (kind, filename) DO NOTHING",
            (user_id, kind, filename),
        )


async def list_owned_filenames(*, kind: str, user_id: str) -> frozenset[str]:
    """Nomes de arquivos (`kind`) gravados em `generated_files` para `user_id`.

    Usada pelas listagens (REQ-003 de `media-ownership-authorization`) para
    filtrar o resultado de uma varredura de diretório aos arquivos do próprio
    usuário. `role admin` não chama esta função — vê a varredura completa,
    sem filtro (ver `images_router.list_images`).
    """
    pool = get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT filename FROM generated_files WHERE kind = %s AND user_id = %s",
            (kind, user_id),
        )
        rows = await cur.fetchall()
    return frozenset(row[0] for row in rows)


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
