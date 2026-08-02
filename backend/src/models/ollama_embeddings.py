"""Embeddings Ollama para o índice vetorial do Store (memória de longo prazo).

O `langgraph.json` referencia a função `embed_texts` em `store.index.embed`.
O modelo padrão é `mxbai-embed-large` (1024 dimensões).
"""
import os

from dotenv import load_dotenv
from langchain_ollama import OllamaEmbeddings

load_dotenv()

OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "mxbai-embed-large")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Dimensão do vetor gerado pelo modelo (deve casar com `store.index.dims`).
EMBED_DIMS = 1024

ollama_embeddings = OllamaEmbeddings(
    model=OLLAMA_EMBED_MODEL,
    base_url=OLLAMA_BASE_URL,
)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Gera embeddings para uma lista de textos.

    Assinatura exigida pelo `store.index.embed` do LangGraph: recebe uma lista de
    strings e retorna a lista de vetores correspondentes.
    """
    return ollama_embeddings.embed_documents(texts)


async def aembed_texts(texts: list[str]) -> list[list[float]]:
    """Gera embeddings para uma lista de textos, sem bloquear o event loop.

    Contraparte async de `embed_texts`, usada por `ScopedSkillsMiddleware.abefore_agent`
    para não bloquear o servidor async ao calcular a relevância de skills por turno.
    """
    return await ollama_embeddings.aembed_documents(texts)
