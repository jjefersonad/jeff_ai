"""Repositório do mapeamento phone_number -> thread_id do canal WhatsApp.

Usa `psycopg` diretamente contra a tabela `whatsapp_threads` (schema.py),
mesmo padrão de `src/infrastructure/telegram/thread_repository.py`. Desde
`whatsapp-slash-commands`, um `phone_number` pode ter múltiplas threads
(histórico de sessões); `get_or_create_thread_id`/`set_active_thread`/
`create_thread_for_number` giram em torno do estado `active` (uma linha
ativa por vez, garantida pelo índice único parcial do schema).
`list_threads_for_number`/`update_thread_title`/`get_thread_by_title` são
leitura/renomeação, sem mexer no estado ativo.
"""

from __future__ import annotations

import os
import uuid

import psycopg

_SELECT_ACTIVE_THREAD_ID = """
SELECT thread_id FROM whatsapp_threads WHERE phone_number = %s AND active = TRUE
"""

_INSERT_NEW_ACTIVE_THREAD = """
INSERT INTO whatsapp_threads (phone_number, thread_id, title, active)
VALUES (%s, %s, %s, TRUE)
"""

_SELECT_THREAD_EXISTS = """
SELECT 1 FROM whatsapp_threads WHERE phone_number = %s AND thread_id = %s
"""

_DEACTIVATE_OTHER_ACTIVE_THREADS = """
UPDATE whatsapp_threads SET active = FALSE
WHERE phone_number = %s AND active = TRUE AND thread_id != %s
"""

_ACTIVATE_THREAD = """
UPDATE whatsapp_threads SET active = TRUE
WHERE phone_number = %s AND thread_id = %s
"""

_SELECT_TITLE_CONFLICT_FOR_NEW_THREAD = """
SELECT 1 FROM whatsapp_threads WHERE phone_number = %s AND title = %s
"""

_DEACTIVATE_ACTIVE_THREAD_FOR_NUMBER = """
UPDATE whatsapp_threads SET active = FALSE WHERE phone_number = %s AND active = TRUE
"""

_LIST_THREADS_FOR_NUMBER = """
SELECT thread_id, title, active, created_at
FROM whatsapp_threads
WHERE phone_number = %s
ORDER BY created_at DESC
LIMIT 20
"""

_SELECT_TITLE_CONFLICT = """
SELECT 1 FROM whatsapp_threads
WHERE phone_number = %s AND title = %s AND thread_id != %s
"""

_UPDATE_THREAD_TITLE = """
UPDATE whatsapp_threads SET title = %s
WHERE phone_number = %s AND thread_id = %s
"""

_SELECT_THREAD_BY_TITLE = """
SELECT thread_id, title, active, created_at
FROM whatsapp_threads
WHERE phone_number = %s AND title = %s
"""


def get_or_create_thread_id(phone_number: str) -> str:
    """Devolve o `thread_id` ATIVO de `phone_number`, criando-o se necessário (REQ-002).

    Um `phone_number` pode ter várias threads (histórico de sessões); esta função
    sempre resolve a linha com `active=TRUE`. Se nenhuma existir, cria uma nova
    já marcada como ativa.
    """
    conninfo = os.environ["POSTGRES_URI"]

    with psycopg.connect(conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_ACTIVE_THREAD_ID, (phone_number,))
            row = cur.fetchone()
            if row is not None:
                return row[0]

            new_thread_id = str(uuid.uuid4())
            cur.execute(_INSERT_NEW_ACTIVE_THREAD, (phone_number, new_thread_id, None))
        conn.commit()

    return new_thread_id


def set_active_thread(phone_number: str, thread_id: str) -> bool:
    """Marca `(phone_number, thread_id)` como a thread ativa do número (REQ-007).

    Desmarca qualquer outra thread ativa do mesmo `phone_number` na mesma
    transação. Retorna `False` sem alterar nada se a thread alvo não existir.
    """
    conninfo = os.environ["POSTGRES_URI"]

    with psycopg.connect(conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_THREAD_EXISTS, (phone_number, thread_id))
            if cur.fetchone() is None:
                return False

            cur.execute(_DEACTIVATE_OTHER_ACTIVE_THREADS, (phone_number, thread_id))
            cur.execute(_ACTIVATE_THREAD, (phone_number, thread_id))
        conn.commit()

    return True


def create_thread_for_number(phone_number: str, title: str | None = None) -> str:
    """Cria uma nova thread para `phone_number`, já marcada ativa (REQ-002).

    Desmarca qualquer thread ativa anterior do mesmo `phone_number` na mesma
    transação. Levanta `ValueError` se `title` já estiver em uso por outra
    thread do mesmo `phone_number`.
    """
    conninfo = os.environ["POSTGRES_URI"]
    new_thread_id = str(uuid.uuid4())

    with psycopg.connect(conninfo) as conn:
        with conn.cursor() as cur:
            if title is not None:
                cur.execute(_SELECT_TITLE_CONFLICT_FOR_NEW_THREAD, (phone_number, title))
                if cur.fetchone() is not None:
                    raise ValueError(
                        f"Título {title!r} já está em uso por outra thread do número "
                        f"{phone_number!r}."
                    )

            cur.execute(_DEACTIVATE_ACTIVE_THREAD_FOR_NUMBER, (phone_number,))
            cur.execute(_INSERT_NEW_ACTIVE_THREAD, (phone_number, new_thread_id, title))
        conn.commit()

    return new_thread_id


def list_threads_for_number(phone_number: str) -> list[dict[str, object]]:
    """Lista até 20 threads de `phone_number`, mais recentes primeiro (REQ-005)."""
    conninfo = os.environ["POSTGRES_URI"]

    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_LIST_THREADS_FOR_NUMBER, (phone_number,))
            rows = cur.fetchall()

    return [
        {"thread_id": r[0], "title": r[1], "active": r[2], "created_at": r[3]} for r in rows
    ]


def update_thread_title(thread_id: str, phone_number: str, title: str) -> bool:
    """Atualiza o `title` de `(phone_number, thread_id)` (REQ-003).

    Levanta `ValueError` se outra thread do mesmo `phone_number` já usa `title`.
    """
    conninfo = os.environ["POSTGRES_URI"]

    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_TITLE_CONFLICT, (phone_number, title, thread_id))
            if cur.fetchone() is not None:
                raise ValueError(
                    f"Título {title!r} já está em uso por outra thread do número "
                    f"{phone_number!r}."
                )

            cur.execute(_UPDATE_THREAD_TITLE, (title, phone_number, thread_id))
            return cur.rowcount > 0


def get_thread_by_title(phone_number: str, title: str) -> dict[str, object] | None:
    """Resolve a thread de `phone_number` com `title`, ou `None` se não houver (REQ-004)."""
    conninfo = os.environ["POSTGRES_URI"]

    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_THREAD_BY_TITLE, (phone_number, title))
            row = cur.fetchone()

    if row is None:
        return None
    return {"thread_id": row[0], "title": row[1], "active": row[2], "created_at": row[3]}
