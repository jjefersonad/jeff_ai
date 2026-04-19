"""arXiv Tool - Search and download full papers from arXiv.

This module provides tools for searching and retrieving complete papers
from arXiv academic repository.
"""

from langchain_core.tools import tool
import json
from datetime import datetime

try:
    import arxiv
except ImportError:
    arxiv = None


@tool
def arxiv_search(query: str, max_results: int = 3) -> str:
    """Search and retrieve full paper information from arXiv.

    This tool searches the arXiv database and returns complete paper
    information including title, authors, abstract, PDF URL, and publication date.

    Args:
        query: Search query for arXiv (supports full arXiv query syntax)
        max_results: Maximum number of papers to return (default: 3)

    Returns:
        JSON-formatted string with paper information including:
        - title: Paper title
        - authors: List of author names
        - summary: Paper abstract
        - pdf_url: Direct link to full PDF
        - published: Publication date
        - arxiv_id: arXiv identifier (e.g., 2301.12345)

    Example:
        >>> result = arxiv_search.invoke({
        ...     "query": "quantum computing applications",
        ...     "max_results": 2
        ... })
    """
    if arxiv is None:
        return "Error: arxiv library not installed. Install with: pip install arxiv"

    try:
        # Search arXiv with configured parameters
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
            sort_order=arxiv.SortOrder.Descending,
        )
        
        # Criar cliente para buscar resultados
        client = arxiv.Client()
        
        results = []
        for paper in client.results(search):
            # Extract complete paper information
            paper_info = {
                "arxiv_id": paper.entry_id.split("/")[-1] if hasattr(paper, 'entry_id') else paper.entry_id,
                "title": paper.title,
                "authors": [author.name for author in paper.authors],
                "summary": paper.summary,
                "pdf_url": paper.pdf_url,
                "published": paper.published.strftime("%Y-%m-%d")
                if paper.published
                else "Unknown",
                "categories": ", ".join(paper.categories)
                if hasattr(paper, 'categories') and paper.categories
                else "Unknown",
                "primary_category": paper.primary_category
                if hasattr(paper, "primary_category")
                else "Unknown",
            }
            results.append(paper_info)

        # Format response for the agent
        if not results:
            return f"No papers found for query: {query}"

        response = {"query": query, "papers_found": len(results), "papers": results}

        return json.dumps(response, indent=2, ensure_ascii=False)

    except Exception as e:
        return f"Error searching arXiv: {str(e)}"


@tool
def arxiv_get_paper(arxiv_id: str) -> str:
    """Get detailed information for a specific arXiv paper by ID.

    Args:
        arxiv_id: arXiv identifier (e.g., "2301.12345" or "quant-ph/2301.12345")

    Returns:
        JSON-formatted string with complete paper details
    """
    if arxiv is None:
        return "Error: arxiv library not installed. Install with: pip install arxiv"

    try:
        # Search by arXiv ID
        search = arxiv.Search(id_list=[arxiv_id])
        client = arxiv.Client()
        paper = next(client.results(search))

        if not paper:
            return f"No paper found with arXiv ID: {arxiv_id}"

        # Extract complete information
        paper_info = {
            "arxiv_id": arxiv_id,
            "title": paper.title,
            "authors": [author.name for author in paper.authors],
            "summary": paper.summary,
            "pdf_url": paper.pdf_url,
            "published": paper.published.strftime("%Y-%m-%d")
            if paper.published
            else "Unknown",
            "categories": ", ".join(paper.categories)
            if hasattr(paper, 'categories') and paper.categories
            else "Unknown",
            "primary_category": paper.primary_category
            if hasattr(paper, "primary_category")
            else "Unknown",
            "links": [link.href for link in paper.links]
            if hasattr(paper, "links")
            else [],
        }

        return json.dumps(paper_info, indent=2, ensure_ascii=False)

    except Exception as e:
        return f"Error getting paper {arxiv_id}: {str(e)}"


# Export tools for agent usage
__all__ = ["arxiv_search", "arxiv_get_paper"]
