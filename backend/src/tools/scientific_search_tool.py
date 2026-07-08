"""Ferramentas de busca de artigos científicos para os agentes do Jeff AI.

Expõe ferramentas LangChain (`@tool`) que consultam repositórios acadêmicos e
retornam artigos em um formato estruturado uniforme.

Fontes:
- arXiv (implementada) — repositório aberto da Cornell, papers de ponta em
  CS/ML/IA, consumido via arXiv Query API (feed Atom).
- SciELO (adiada) — `search.scielo.org` está atrás de um escudo anti-bot com
  desafio JavaScript que impede acesso confiável por cliente HTTP de servidor;
  ver `busca-artigos-cientificos-design` no OpenSddRag.
"""

import xml.etree.ElementTree as ET

import httpx
from langchain_core.tools import tool

_ARXIV_API_URL = "https://export.arxiv.org/api/query"
_HTTP_TIMEOUT = 20.0

# Namespaces do feed Atom retornado pela arXiv Query API.
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def _normalize_article(
    *,
    title: str,
    authors: list[str],
    summary: str,
    published: str,
    url: str,
    source: str,
) -> dict:
    """Monte um artigo no formato estruturado uniforme entre as fontes."""
    return {
        "title": (title or "").strip(),
        "authors": [a.strip() for a in authors if a and a.strip()],
        "summary": (summary or "").strip(),
        "published": (published or "").strip(),
        "url": (url or "").strip(),
        "source": source,
    }


def _parse_arxiv_feed(xml_text: str) -> list[dict]:
    """Converta o feed Atom do arXiv em uma lista de artigos normalizados."""
    root = ET.fromstring(xml_text)
    articles: list[dict] = []
    for entry in root.findall("atom:entry", _ATOM_NS):
        title = entry.findtext("atom:title", default="", namespaces=_ATOM_NS)
        summary = entry.findtext("atom:summary", default="", namespaces=_ATOM_NS)
        published = entry.findtext("atom:published", default="", namespaces=_ATOM_NS)
        url = entry.findtext("atom:id", default="", namespaces=_ATOM_NS)
        authors = [
            name
            for author in entry.findall("atom:author", _ATOM_NS)
            if (name := author.findtext("atom:name", default="", namespaces=_ATOM_NS))
        ]
        articles.append(
            _normalize_article(
                title=title,
                authors=authors,
                summary=summary,
                published=published,
                url=url,
                source="arxiv",
            )
        )
    return articles


@tool
def search_arxiv(query: str, max_results: int = 5) -> list[dict] | str:
    """Busque artigos científicos no arXiv (CS, aprendizado de máquina, IA).

    Args:
        query: Termos de busca em linguagem natural (ex.: "large language models").
        max_results: Número máximo de artigos a retornar (padrão 5).

    Returns:
        Lista de artigos, cada um com as chaves ``title``, ``authors``,
        ``summary``, ``published``, ``url`` e ``source``. Retorna lista vazia
        quando não há resultados e uma mensagem de erro (str) em caso de falha.
    """
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
    }
    try:
        response = httpx.get(
            _ARXIV_API_URL,
            params=params,
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
        )
        response.raise_for_status()
        return _parse_arxiv_feed(response.text)
    except httpx.HTTPError as exc:
        return f"Erro ao consultar o arXiv: {exc}"
    except ET.ParseError as exc:
        return f"Erro ao processar a resposta do arXiv: {exc}"
