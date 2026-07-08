import os
from functools import lru_cache
from typing import Literal
from tavily import TavilyClient
from langchain_core.tools import tool


@lru_cache
def _get_tavily_client() -> TavilyClient:
    """Lazy initialization of TavilyClient to avoid startup failures when TAVILY_API_KEY is not set."""
    return TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


@tool
def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
):
    """Run a web search"""
    return _get_tavily_client().search(
        query,
        max_results=max_results,
        include_raw_content=include_raw_content,
        topic=topic,
    )