"""Testes da tool `internet_search` (REQ-006 de `current-date-context`).

O cliente Tavily é sempre mockado — nenhum teste faz chamada real de rede.
Cobre: sufixo `as_of_date` explícito, omitido (default = hoje), formato
inválido (sem chamar Tavily), e datas no passado distante/futuro (aceitas
sem filtro de range).
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import src.tools.tavily_tool as tt


def _mock_client() -> MagicMock:
    client = MagicMock()
    client.search.return_value = {"results": []}
    return client


def test_as_of_date_explicit_suffixes_query():
    client = _mock_client()
    with patch.object(tt, "_get_tavily_client", return_value=client):
        tt.internet_search.invoke({"query": "notícias de IA", "as_of_date": "2026-07-13"})

    called_query = client.search.call_args[0][0]
    assert called_query == "notícias de IA (as of 2026-07-13)"


def test_as_of_date_omitted_uses_today(monkeypatch):
    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 14, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr(tt, "datetime", _FrozenDatetime)
    client = _mock_client()
    with patch.object(tt, "_get_tavily_client", return_value=client):
        tt.internet_search.invoke({"query": "história do transformer"})

    called_query = client.search.call_args[0][0]
    assert called_query == "história do transformer (as of 2026-07-14)"


def test_as_of_date_invalid_format_returns_error():
    client = _mock_client()
    with patch.object(tt, "_get_tavily_client", return_value=client):
        result = tt.internet_search.invoke({"query": "X", "as_of_date": "ontem"})

    client.search.assert_not_called()
    assert "YYYY-MM-DD" in result


def test_as_of_date_distant_past_accepted():
    client = _mock_client()
    with patch.object(tt, "_get_tavily_client", return_value=client):
        tt.internet_search.invoke({"query": "histórico", "as_of_date": "1995-01-01"})

    called_query = client.search.call_args[0][0]
    assert called_query == "histórico (as of 1995-01-01)"


def test_as_of_date_future_accepted():
    client = _mock_client()
    with patch.object(tt, "_get_tavily_client", return_value=client):
        tt.internet_search.invoke({"query": "X", "as_of_date": "2099-12-31"})

    called_query = client.search.call_args[0][0]
    assert called_query == "X (as of 2099-12-31)"
