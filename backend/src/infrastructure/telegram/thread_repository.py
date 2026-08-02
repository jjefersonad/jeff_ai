"""Repositório do mapeamento chat_id -> thread_id do canal Telegram.

Usa `psycopg` diretamente contra a tabela `telegram_threads` (schema.py), sem
pool dedicado: a função é chamada uma vez por mensagem recebida pelo
`telegram_gateway.py`, que abre seu próprio pool separadamente para o resto
do processamento (ver design da mudança `integracao-telegram`).
"""

from __future__ import annotations

import os
import uuid

import psycopg

_SELECT_ACTIVE_THREAD_ID = """
SELECT thread_id FROM telegram_threads WHERE chat_id = %s AND active = TRUE
"""

_INSERT_NEW_ACTIVE_THREAD = """
INSERT INTO telegram_threads (chat_id, thread_id, title, active)
VALUES (%s, %s, %s, TRUE)
"""

_SELECT_THREAD_EXISTS = """
SELECT 1 FROM telegram_threads WHERE chat_id = %s AND thread_id = %s
"""

_DEACTIVATE_OTHER_ACTIVE_THREADS = """
UPDATE telegram_threads SET active = FALSE
WHERE chat_id = %s AND active = TRUE AND thread_id != %s
"""

_ACTIVATE_THREAD = """
UPDATE telegram_threads SET active = TRUE
WHERE chat_id = %s AND thread_id = %s
"""

_SELECT_TITLE_CONFLICT_FOR_NEW_THREAD = """
SELECT 1 FROM telegram_threads WHERE chat_id = %s AND title = %s
"""

_DEACTIVATE_ACTIVE_THREAD_FOR_CHAT = """
UPDATE telegram_threads SET active = FALSE WHERE chat_id = %s AND active = TRUE
"""

_LIST_THREADS_FOR_CHAT = """
SELECT thread_id, title, active, created_at
FROM telegram_threads
WHERE chat_id = %s
ORDER BY created_at DESC
LIMIT 20
"""

_SELECT_TITLE_CONFLICT = """
SELECT 1 FROM telegram_threads
WHERE chat_id = %s AND title = %s AND thread_id != %s
"""

_UPDATE_THREAD_TITLE = """
UPDATE telegram_threads SET title = %s
WHERE chat_id = %s AND thread_id = %s
"""

_SELECT_THREAD_BY_TITLE = """
SELECT thread_id, title, active, created_at
FROM telegram_threads
WHERE chat_id = %s AND title = %s
"""


def get_or_create_thread_id(chat_id: str) -> str:
    """Devolve o `thread_id` ativo de `chat_id`, criando-o se necessário (REQ-001).

    Um `chat_id` pode ter várias threads (histórico de sessões); esta função
    sempre resolve a linha com `active=TRUE`. Se nenhuma existir, cria uma
    nova já marcada como ativa.
    """
    conninfo = os.environ["POSTGRES_URI"]

    with psycopg.connect(conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_ACTIVE_THREAD_ID, (chat_id,))
            row = cur.fetchone()
            if row is not None:
                return row[0]

            new_thread_id = str(uuid.uuid4())
            cur.execute(_INSERT_NEW_ACTIVE_THREAD, (chat_id, new_thread_id, None))
        conn.commit()

    return new_thread_id


def set_active_thread(chat_id: str, thread_id: str) -> bool:
    """Marca `(chat_id, thread_id)` como a thread ativa do chat (REQ-005).

    Desmarca qualquer outra thread ativa do mesmo `chat_id` na mesma
    transação. Retorna `False` sem alterar nada se a thread alvo não existir.
    """
    conninfo = os.environ["POSTGRES_URI"]

    with psycopg.connect(conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_THREAD_EXISTS, (chat_id, thread_id))
            if cur.fetchone() is None:
                return False

            cur.execute(_DEACTIVATE_OTHER_ACTIVE_THREADS, (chat_id, thread_id))
            cur.execute(_ACTIVATE_THREAD, (chat_id, thread_id))
        conn.commit()

    return True


def create_thread_for_chat(chat_id: str, title: str | None = None) -> str:
    """Cria uma nova thread para `chat_id`, já marcada ativa (REQ-006).

    Desmarca qualquer thread ativa anterior do mesmo `chat_id` na mesma
    transação. Levanta `ValueError` se `title` já estiver em uso por outra
    thread do mesmo `chat_id`.
    """
    conninfo = os.environ["POSTGRES_URI"]
    new_thread_id = str(uuid.uuid4())

    with psycopg.connect(conninfo) as conn:
        with conn.cursor() as cur:
            if title is not None:
                cur.execute(_SELECT_TITLE_CONFLICT_FOR_NEW_THREAD, (chat_id, title))
                if cur.fetchone() is not None:
                    raise ValueError(
                        f"Título {title!r} já está em uso por outra thread do chat {chat_id!r}."
                    )

            cur.execute(_DEACTIVATE_ACTIVE_THREAD_FOR_CHAT, (chat_id,))
            cur.execute(_INSERT_NEW_ACTIVE_THREAD, (chat_id, new_thread_id, title))
        conn.commit()

    return new_thread_id


def list_threads_for_chat(chat_id: str) -> list[dict[str, object]]:
    """Lista até 20 threads de `chat_id`, mais recentes primeiro (REQ-002)."""
    conninfo = os.environ["POSTGRES_URI"]

    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_LIST_THREADS_FOR_CHAT, (chat_id,))
            rows = cur.fetchall()

    return [
        {"thread_id": r[0], "title": r[1], "active": r[2], "created_at": r[3]} for r in rows
    ]


def update_thread_title(thread_id: str, chat_id: str, title: str) -> bool:
    """Atualiza o `title` de `(chat_id, thread_id)` (REQ-003).

    Levanta `ValueError` se outra thread do mesmo `chat_id` já usa `title`.
    """
    conninfo = os.environ["POSTGRES_URI"]

    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_TITLE_CONFLICT, (chat_id, title, thread_id))
            if cur.fetchone() is not None:
                raise ValueError(
                    f"Título {title!r} já está em uso por outra thread do chat {chat_id!r}."
                )

            cur.execute(_UPDATE_THREAD_TITLE, (title, chat_id, thread_id))
            return cur.rowcount > 0


def get_thread_by_title(chat_id: str, title: str) -> dict[str, object] | None:
    """Resolve a thread de `chat_id` com `title`, ou `None` se não houver (REQ-004)."""
    conninfo = os.environ["POSTGRES_URI"]

    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_THREAD_BY_TITLE, (chat_id, title))
            row = cur.fetchone()

    if row is None:
        return None
    return {"thread_id": row[0], "title": row[1], "active": row[2], "created_at": row[3]}
