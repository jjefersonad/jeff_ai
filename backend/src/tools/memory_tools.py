"""Ferramentas de memória de longo prazo, compartilhada entre TODAS as threads.

Usam o Store do LangGraph (Postgres/pgvector). A busca é semântica quando o
`store.index` está configurado com embeddings (ver `langgraph.json` e
`src/models/ollama_embeddings.py`).

O namespace é fixo e global (`("memories",)`), então uma memória salva numa
thread pode ser recuperada em qualquer outra.
"""
import uuid

from langchain_core.tools import tool
from langgraph.config import get_store

# Namespace cross-thread: memórias salvas aqui não são presas a um thread_id.
MEMORY_NAMESPACE = ("memories",)


@tool
async def save_memory(content: str) -> str:
    """Salva um fato, decisão ou preferência importante na memória de longo prazo.

    Use quando o usuário informar algo que valha a pena lembrar em conversas
    futuras (nomes, preferências, decisões de projeto, contexto recorrente).
    A memória fica disponível em QUALQUER thread futura via `search_memory`.
    """
    store = get_store()
    key = str(uuid.uuid4())
    await store.aput(MEMORY_NAMESPACE, key, {"content": content})
    return "Memória salva com sucesso."


@tool
async def search_memory(query: str, limit: int = 5) -> str:
    """Busca na memória de longo prazo (todas as threads) por similaridade semântica.

    Use ANTES de responder quando o usuário se referir a algo do passado, a uma
    decisão anterior, ou quando precisar de contexto que não está na conversa atual.
    """
    store = get_store()
    results = await store.asearch(MEMORY_NAMESPACE, query=query, limit=limit)
    if not results:
        return "Nenhuma memória relevante encontrada."
    return "\n".join(f"- {item.value.get('content', '')}" for item in results)
