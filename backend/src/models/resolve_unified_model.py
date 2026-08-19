"""Resolvedor de `model_override` — os mesmos backends do grafo `unified`.

Empírico (runtime-3): `unified_model` é `FallbackChatModel(primary=ollama_model,
fallback=openrouter_model)`. `gemini_model` existe no repo mas **não** entra
no grafo. `ChatOllama(model=...)` aceita qualquer string no construtor, então
fail-closed não pode depender do ctor — só nomes do catálogo abaixo resolvem.
"""
from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from src.domain.agents import InvalidModelOverrideError
from src.models.fallback_model import unified_model
from src.models.ollama_model import ollama_model
from src.models.openrouter_model import openrouter_model

_ALIAS_UNIFIED = "unified"
_ALIAS_OLLAMA = "ollama"
_ALIAS_OPENROUTER = "openrouter"


def _catalog() -> dict[str, BaseChatModel]:
    """Aliases + ids atuais das instâncias usadas por `unified_model`."""
    catalog: dict[str, BaseChatModel] = {
        _ALIAS_UNIFIED: unified_model,
        _ALIAS_OLLAMA: ollama_model,
        _ALIAS_OPENROUTER: openrouter_model,
    }
    ollama_id = getattr(ollama_model, "model", None)
    if ollama_id:
        catalog[str(ollama_id)] = ollama_model
    openrouter_id = getattr(openrouter_model, "model", None)
    if openrouter_id:
        catalog[str(openrouter_id)] = openrouter_model
    return catalog


def resolve_unified_model(name: str) -> BaseChatModel:
    """Devolve o backend do grafo para `name`, ou falha fechado.

    Aceita `unified` / `ollama` / `openrouter` e os ids `.model` atuais dessas
    instâncias. Qualquer outro valor (incluindo `gemini`) levanta
    `InvalidModelOverrideError`.
    """
    key = name.strip() if isinstance(name, str) else ""
    if not key:
        raise InvalidModelOverrideError("model_override inválido: nome vazio")
    resolved = _catalog().get(key)
    if resolved is None:
        raise InvalidModelOverrideError(f"model_override inválido: {key!r}")
    return resolved


__all__ = ["resolve_unified_model"]
