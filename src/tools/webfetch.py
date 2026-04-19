"""Tools for fetching web content."""

from langchain_core.tools import tool
import requests


@tool
def webfetch(url: str, timeout: int = 30) -> str:
    """Fetch the content of a URL.

    Args:
        url: The URL to fetch
        timeout: Request timeout in seconds (default: 30)

    Returns:
        The content of the URL or error message
    """
    # Validate URL
    if not url.startswith(("http://", "https://")):
        return f"Error: Invalid URL format: {url}"

    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AgentBot/1.0)"}
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()

        # Limit response size
        max_size = 51200  # 50KB
        content = response.text

        if len(content.encode("utf-8")) > max_size:
            truncated = content[:max_size]
            return (
                f"[Response truncated at {max_size} bytes]\n\n"
                f"{truncated}\n\n"
                f"[... full response available at {url}]"
            )

        return content
    except requests.exceptions.Timeout:
        return f"Error: Request timed out after {timeout}s"
    except requests.exceptions.HTTPError as e:
        return f"Error: HTTP {e.response.status_code} - {e.response.reason}"
    except requests.exceptions.RequestException as e:
        return f"Error fetching {url}: {str(e)}"
