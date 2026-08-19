"""Catálogo empírico de `resolve_unified_model` (runtime-3 / REQ-001)."""
from __future__ import annotations

import pytest

from src.domain.agents import InvalidModelOverrideError
from src.models.fallback_model import unified_model
from src.models.ollama_model import ollama_model
from src.models.openrouter_model import openrouter_model
from src.models.resolve_unified_model import resolve_unified_model


def test_aliases_map_to_unified_graph_backends() -> None:
    assert resolve_unified_model("unified") is unified_model
    assert resolve_unified_model("ollama") is ollama_model
    assert resolve_unified_model("openrouter") is openrouter_model


def test_instance_model_ids_map_to_same_backends() -> None:
    assert resolve_unified_model(str(ollama_model.model)) is ollama_model
    assert resolve_unified_model(str(openrouter_model.model)) is openrouter_model


@pytest.mark.parametrize("name", ["gemini", "not-a-real-model", "", "  "])
def test_unknown_names_fail_closed(name: str) -> None:
    with pytest.raises(InvalidModelOverrideError, match="model_override"):
        resolve_unified_model(name)
