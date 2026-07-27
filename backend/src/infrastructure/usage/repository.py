"""Repositório de eventos de uso de tokens (`token_usage_events`).

`record` persiste um evento e é fail-open (erro de I/O não propaga).
`aggregate` soma tokens com filtros opcionais (somente leitura).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import psycopg

logger = logging.getLogger(__name__)

_INSERT_EVENT = """
INSERT INTO token_usage_events (
    user_key, thread_id, provider, model,
    prompt_tokens, completion_tokens, total_tokens, source
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""


class UsageRepository:
    """Persistência e agregação de eventos de uso de tokens."""

    def __init__(self, conninfo: str) -> None:
        """Guarda o conninfo Postgres para abrir conexões em cada operação."""
        self._conninfo = conninfo

    def record(
        self,
        *,
        user_key: str,
        thread_id: str | None,
        provider: str,
        model: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        total_tokens: int | None,
        source: str,
    ) -> None:
        """Grava um evento de uso. Falhas de DB são engolidas e logadas."""
        try:
            with psycopg.connect(self._conninfo) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        _INSERT_EVENT,
                        (
                            user_key,
                            thread_id,
                            provider,
                            model,
                            prompt_tokens,
                            completion_tokens,
                            total_tokens,
                            source,
                        ),
                    )
                conn.commit()
        except Exception:
            logger.exception("Failed to record token usage event")

    def aggregate(
        self,
        *,
        user_key: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Soma tokens com filtros opcionais. Somente leitura; zeros se vazio."""
        clauses: list[str] = []
        params: list[object] = []
        filters: dict[str, object] = {}

        if user_key is not None:
            clauses.append("user_key = %s")
            params.append(user_key)
            filters["user_key"] = user_key
        if from_ts is not None:
            clauses.append("created_at >= %s")
            params.append(from_ts)
            filters["from"] = from_ts
        if to_ts is not None:
            clauses.append("created_at <= %s")
            params.append(to_ts)
            filters["to"] = to_ts
        if provider is not None:
            clauses.append("provider = %s")
            params.append(provider)
            filters["provider"] = provider
        if model is not None:
            clauses.append("model = %s")
            params.append(model)
            filters["model"] = model

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
SELECT
    COALESCE(SUM(prompt_tokens), 0),
    COALESCE(SUM(completion_tokens), 0),
    COALESCE(SUM(total_tokens), 0)
FROM token_usage_events
{where}
"""
        with psycopg.connect(self._conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                row = cur.fetchone()

        prompt_tokens, completion_tokens, total_tokens = row or (0, 0, 0)
        result: dict[str, Any] = {
            "prompt_tokens": int(prompt_tokens),
            "completion_tokens": int(completion_tokens),
            "total_tokens": int(total_tokens),
            "filters": filters,
        }
        if user_key is not None:
            result["user_key"] = user_key
        return result
