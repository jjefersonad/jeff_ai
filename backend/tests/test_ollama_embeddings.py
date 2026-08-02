"""Testes da capability `semantic-skill-relevance` (change semantic-skill-relevance-filtering).

Cobre REQ-003 (o embedding da conversa/skills usa o caminho async do
OllamaEmbeddings quando o agente roda de forma assíncrona, sem bloquear o
event loop).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from langchain_ollama import OllamaEmbeddings

from src.models import ollama_embeddings


async def test_aembed_texts_uses_async_path():
    """REQ-003: `aembed_texts` chama `aembed_documents` (não o `embed_documents` síncrono)."""
    fake_vectors = [[0.1, 0.2, 0.3]]
    with (
        patch.object(
            OllamaEmbeddings,
            "aembed_documents",
            new=AsyncMock(return_value=fake_vectors),
        ) as mock_aembed,
        patch.object(OllamaEmbeddings, "embed_documents") as mock_embed_sync,
    ):
        result = await ollama_embeddings.aembed_texts(["hello"])

    mock_aembed.assert_awaited_once_with(["hello"])
    mock_embed_sync.assert_not_called()
    assert result == fake_vectors
