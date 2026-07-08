"""Testes da ferramenta search_arxiv.

O cliente HTTP (`httpx.get`) é mockado — nenhum teste faz chamada real de rede.
Cobre: busca com resultados (REQ-001/002), zero resultados (edge) e resiliência
a falhas de rede/parse (REQ-003).
"""
from unittest.mock import MagicMock, patch

import httpx

import src.tools.scientific_search_tool as st

_ATOM_FEED = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2501.00001v1</id>
    <title>Attention Is All You Need Again</title>
    <summary>Um resumo de teste sobre transformers.</summary>
    <published>2025-01-02T00:00:00Z</published>
    <author><name>Ada Lovelace</name></author>
    <author><name>Alan Turing</name></author>
  </entry>
</feed>"""

_EMPTY_FEED = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom">
</feed>"""


def _mock_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.raise_for_status.return_value = None
    return resp


def test_search_arxiv_returns_normalized_articles():
    """REQ-001/002: retorna artigos com todas as chaves estruturadas."""
    with patch.object(st.httpx, "get", return_value=_mock_response(_ATOM_FEED)):
        result = st.search_arxiv.invoke({"query": "transformers", "max_results": 5})

    assert isinstance(result, list)
    assert len(result) == 1
    article = result[0]
    assert set(article.keys()) == {
        "title",
        "authors",
        "summary",
        "published",
        "url",
        "source",
    }
    assert article["title"] == "Attention Is All You Need Again"
    assert article["authors"] == ["Ada Lovelace", "Alan Turing"]
    assert article["summary"] == "Um resumo de teste sobre transformers."
    assert article["published"] == "2025-01-02T00:00:00Z"
    assert article["url"] == "http://arxiv.org/abs/2501.00001v1"
    assert article["source"] == "arxiv"


def test_search_arxiv_no_results_returns_empty_list():
    """Edge: consulta sem resultados retorna lista vazia, sem exceção."""
    with patch.object(st.httpx, "get", return_value=_mock_response(_EMPTY_FEED)):
        result = st.search_arxiv.invoke({"query": "nadaexistente"})

    assert result == []


def test_search_arxiv_network_error_returns_message():
    """REQ-003: falha de rede é capturada e retorna mensagem de erro (str)."""
    with patch.object(st.httpx, "get", side_effect=httpx.ConnectError("boom")):
        result = st.search_arxiv.invoke({"query": "transformers"})

    assert isinstance(result, str)
    assert "arXiv" in result


def test_search_arxiv_invalid_xml_returns_message():
    """REQ-003: resposta malformada é capturada e retorna mensagem de erro (str)."""
    with patch.object(st.httpx, "get", return_value=_mock_response("<not-xml")):
        result = st.search_arxiv.invoke({"query": "transformers"})

    assert isinstance(result, str)
    assert "arXiv" in result
