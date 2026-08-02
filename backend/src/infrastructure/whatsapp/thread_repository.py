"""Repositório do mapeamento phone_number -> thread_id do canal WhatsApp.

Usa `psycopg` diretamente contra a tabela `whatsapp_threads` (schema.py),
mesmo padrão de `src/infrastructure/telegram/thread_repository.py`
simplificado: um único `thread_id` por `phone_number`, sem o histórico de
múltiplas sessões (`active`/`title`) que telegram-slash-commands adicionou
ao Telegram — fora de escopo deste change (`whatsapp-evolution-channel-
design`).
"""

from __future__ import annotations

import os
import uuid

import psycopg

_SELECT_THREAD_ID = """
SELECT thread_id FROM whatsapp_threads WHERE phone_number = %s
"""

_INSERT_THREAD = """
INSERT INTO whatsapp_threads (phone_number, thread_id)
VALUES (%s, %s)
"""


def get_or_create_thread_id(phone_number: str) -> str:
    """Devolve o `thread_id` de `phone_number`, criando-o se necessário (REQ-002)."""
    conninfo = os.environ["POSTGRES_URI"]

    with psycopg.connect(conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_THREAD_ID, (phone_number,))
            row = cur.fetchone()
            if row is not None:
                return row[0]

            new_thread_id = str(uuid.uuid4())
            cur.execute(_INSERT_THREAD, (phone_number, new_thread_id))
        conn.commit()

    return new_thread_id
