from typing import List, Dict, Optional
import requests
import xml.etree.ElementTree as ET
from langchain_core.tools import tool

@tool
def inovacao_tecnologica_rss(limit: Optional[int] = 10) -> List[Dict[str, str]]:
    """
    Lê o feed RSS do site Inovação Tecnológica (https://www.inovacaotecnologica.com.br/boletim/rss.xml)
    e retorna as últimas notícias com título, link, descrição e data de publicação.

    Args:
        limit: Número máximo de notícias a retornar (padrão: 10).

    Returns:
        Lista de dicionários com as chaves: title, link, description, pub_date.
    """
    url = "https://www.inovacaotecnologica.com.br/boletim/rss.xml"
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.content)

    # O RSS pode ter namespace ou não; tentamos ambos
    ns = {"rss": "http://purl.org/rss/1.0/", "content": "http://purl.org/rss/1.0/modules/content/"}

    items = []
    # Procura por <item> em qualquer lugar do XML
    for item in root.iter("item"):
        title = item.findtext("title", default="").strip()
        link = item.findtext("link", default="").strip()
        description = item.findtext("description", default="").strip()
        pub_date = item.findtext("pubDate", default="").strip()

        items.append({
            "title": title,
            "link": link,
            "description": description,
            "pub_date": pub_date,
        })

        if limit and len(items) >= limit:
            break

    return items
