"""Tool `internet_search` — wrapper sobre a API Tavily com filtro temporal opcional.

A change `current-date-context` adicionou o parâmetro `as_of_date` (formato ISO
`YYYY-MM-DD`). Quando omitido, a data atual do sistema é computada no momento
da chamada via `_resolve_tz()` (compartilhado com `src.agents.unified.agent`).
O sufixo `" (as of YYYY-MM-DD)"` é appended à query antes de chamar Tavily
para dar ao search engine uma pista de freshness sem depender do plano
pago da Tavily (que tem `start_date`/`end_date` nativos).

Por que sufixo e não parâmetro nativo: Tavily free tier não tem `start_date`.
O sufixo funciona em qualquer plano. Se o ranking piorar empiricamente,
follow-up pode migrar para `start_date` nativo (D2 do design).

Por que o helper `_resolve_tz` (e não `datetime.now()` direto): o mesmo
timezone do system prompt é usado aqui. Se o dev configurou
`JEFF_AI_TZ=America/Sao_Paulo`, a data exibida no prompt E a data sufixada
na query batem. Sem isso, o usuário poderia ver "2026-07-14" no prompt e
a Tavily buscar "as of 2026-07-13" (1 dia atrás por causa do offset).
"""
from __future__ import annotations

import os
from datetime import datetime
from functools import lru_cache
from typing import Literal

from langchain_core.tools import tool
from tavily import TavilyClient

from src.agents.unified.datetime_utils import _resolve_tz


@lru_cache
def _get_tavily_client() -> TavilyClient:
    """Lazy initialization of TavilyClient to avoid startup failures when TAVILY_API_KEY is not set."""
    return TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


def _resolve_as_of_date(as_of_date: str | None) -> str | None:
    """Resolve `as_of_date` para uso como sufixo de query.

    - `None` → usa a data atual (computada no momento da chamada, não no
      import — para não estagnar em processos long-running).
    - String no formato ISO `YYYY-MM-DD` → aceita e retorna.
    - String em formato inválido → retorna mensagem de erro (string
      especial `__error__:...` consumida pelo chamador).

    Returns:
        str ISO se OK; str de erro começando com `__error__:` se inválido.
    """
    if as_of_date is None:
        return datetime.now(_resolve_tz()).date().isoformat()
    # Validação: tenta parsear. Se não bater, retorna erro.
    try:
        datetime.strptime(as_of_date, "%Y-%m-%d")
    except ValueError:
        return f"__error__:as_of_date deve estar no formato YYYY-MM-DD; recebi {as_of_date!r}"
    return as_of_date


@tool
def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
    as_of_date: str | None = None,
):
    """Run a web search.

    `as_of_date` (opcional) é um ISO date `YYYY-MM-DD` que
    vira sufixo da query (`" (as of YYYY-MM-DD)"`) — dá ao search engine uma
    pista de freshness. Default: data atual do sistema. Sempre confira a
    data no topo do system prompt antes de chamar esta tool (ver skill
    `internet-search`).
    """
    resolved = _resolve_as_of_date(as_of_date)
    if resolved.startswith("__error__:"):
        return resolved[len("__error__:"):]
    enriched_query = f"{query} (as of {resolved})"
    return _get_tavily_client().search(
        enriched_query,
        max_results=max_results,
        include_raw_content=include_raw_content,
        topic=topic,
    )
