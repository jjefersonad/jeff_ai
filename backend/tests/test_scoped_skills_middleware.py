"""Testes da capability `semantic-skill-relevance` (change semantic-skill-relevance-filtering).

Cobre REQ-004 (cache de embedding de skill por hash de conteúdo, invalidado
quando o conteúdo muda) e o helper `cosine_similarity` usado para decidir
relevância.
"""
from __future__ import annotations

import pytest
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import HumanMessage

from src.agents.unified import scoped_skills_middleware as mod
from src.agents.unified.scoped_skills_middleware import ScopedSkillsMiddleware


@pytest.fixture(autouse=True)
def _clear_skill_embedding_cache():
    """Evita que o cache em memória vaze estado entre testes."""
    mod._skill_embedding_cache.clear()
    yield
    mod._skill_embedding_cache.clear()


def _skill(name: str, description: str):
    return {
        "path": f"/skills/{name}/SKILL.md",
        "name": name,
        "description": description,
        "license": None,
        "compatibility": None,
        "metadata": {},
        "allowed_tools": [],
    }


def _middleware() -> ScopedSkillsMiddleware:
    # `_get_backend` só é acionado quando `skills_metadata` ainda não está no
    # state (ver `before_agent`); todo teste abaixo já popula `skills_metadata`,
    # então um backend/sources dummy nunca chega a ser usado de verdade.
    return ScopedSkillsMiddleware(backend="dummy-backend", sources=["/skills/"])


def test_skill_embedding_cache_reuses_unchanged_content():
    """REQ-004: mesmo hash de conteúdo -> embed_fn chamada só uma vez."""
    calls: list[list[str]] = []

    def fake_embed(texts: list[str]) -> list[list[float]]:
        calls.append(texts)
        return [[1.0, 0.0, 0.0]]

    skill = _skill("diagram-creator", "Represent architecture as Mermaid diagrams")

    first = mod._get_or_embed_skill(skill, fake_embed)
    second = mod._get_or_embed_skill(skill, fake_embed)

    assert first == second == [1.0, 0.0, 0.0]
    assert len(calls) == 1


def test_skill_embedding_cache_invalidates_on_changed_content():
    """REQ-004: descrição diferente -> hash diferente -> embed_fn chamada de novo."""
    calls: list[list[str]] = []

    def fake_embed(texts: list[str]) -> list[list[float]]:
        calls.append(texts)
        return [[float(len(calls)), 0.0, 0.0]]

    skill_v1 = _skill("diagram-creator", "Represent architecture as Mermaid diagrams")
    skill_v2 = _skill("diagram-creator", "Represent architecture as Mermaid diagrams v2")

    mod._get_or_embed_skill(skill_v1, fake_embed)
    mod._get_or_embed_skill(skill_v2, fake_embed)

    assert len(calls) == 2


def test_cosine_similarity_identical_vectors():
    """Vetores idênticos -> similaridade 1.0 (tolerância de ponto flutuante)."""
    v = [0.5, 0.5, 0.5]
    assert mod.cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors():
    """Vetores ortogonais -> similaridade 0.0."""
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert mod.cosine_similarity(a, b) == pytest.approx(0.0)


# --- before_agent / abefore_agent (task-middleware-2) -----------------------


def test_before_agent_computes_relevant_skill_names_via_similarity(monkeypatch):
    """REQ-001: skill semanticamente próxima da conversa entra; a distante, não."""
    skill_close = _skill("diagram-creator", "diagrams")
    skill_far = _skill("pptx", "presentations")

    def fake_embed(texts: list[str]) -> list[list[float]]:
        text = texts[0]
        return [[1.0, 0.0]] if "diagram" in text.lower() else [[0.0, 1.0]]

    monkeypatch.setattr(mod, "embed_texts", fake_embed)

    state = {
        "skills_metadata": [skill_close, skill_far],
        "messages": [HumanMessage(content="quero um diagrama")],
    }
    update = _middleware().before_agent(state, runtime=None, config={})

    assert update is not None
    assert update["relevant_skill_names"] == ["diagram-creator"]


async def test_abefore_agent_uses_async_embedding_path(monkeypatch):
    """REQ-003: `abefore_agent` usa `aembed_texts` (async), nunca `embed_texts` (sync)."""
    calls = {"sync": 0, "async": 0}

    def fake_embed_sync(texts: list[str]) -> list[list[float]]:
        calls["sync"] += 1
        return [[1.0, 0.0]]

    async def fake_aembed(texts: list[str]) -> list[list[float]]:
        calls["async"] += 1
        return [[1.0, 0.0]]

    monkeypatch.setattr(mod, "embed_texts", fake_embed_sync)
    monkeypatch.setattr(mod, "aembed_texts", fake_aembed)

    skill = _skill("diagram-creator", "diagrams")
    state = {
        "skills_metadata": [skill],
        "messages": [HumanMessage(content="diagram please")],
    }
    await _middleware().abefore_agent(state, runtime=None, config={})

    assert calls["async"] > 0
    assert calls["sync"] == 0


def test_before_agent_fails_open_on_embedding_exception(monkeypatch):
    """REQ-005: exceção no embedding -> `relevant_skill_names = None` (não propaga)."""

    def raising_embed(texts: list[str]) -> list[list[float]]:
        raise RuntimeError("ollama unreachable")

    monkeypatch.setattr(mod, "embed_texts", raising_embed)

    skill = _skill("diagram-creator", "diagrams")
    state = {"skills_metadata": [skill], "messages": [HumanMessage(content="oi")]}

    update = _middleware().before_agent(state, runtime=None, config={})

    assert update is not None
    assert update["relevant_skill_names"] is None


def test_before_agent_fails_open_on_zero_matches(monkeypatch):
    """REQ-005: nenhuma skill cruza o limiar -> `relevant_skill_names = None`, não lista vazia."""

    def fake_embed(texts: list[str]) -> list[list[float]]:
        text = texts[0]
        return [[0.0, 1.0]] if "skill" in text else [[1.0, 0.0]]

    monkeypatch.setattr(mod, "embed_texts", fake_embed)

    skill = _skill("some-skill", "unrelated description")
    state = {"skills_metadata": [skill], "messages": [HumanMessage(content="hello world")]}

    update = _middleware().before_agent(state, runtime=None, config={})

    assert update is not None
    assert update["relevant_skill_names"] is None


# --- modify_request (task-middleware-3) --------------------------------------


def _request(state: dict) -> ModelRequest:
    return ModelRequest(  # type: ignore[arg-type]
        model=None,
        messages=state.get("messages", []),
        state=state,
    )


def test_modify_request_filters_by_relevant_skill_names_when_present():
    """ADDED (delta): só as skills em `relevant_skill_names` entram no prompt."""
    skill_a = _skill("skill-a", "Skill A description")
    skill_b = _skill("skill-b", "Skill B description")
    state = {
        "skills_metadata": [skill_a, skill_b],
        "relevant_skill_names": ["skill-a"],
    }

    request = _middleware().modify_request(_request(state))

    prompt_text = request.system_message.text if request.system_message else ""
    assert "skill-a" in prompt_text
    assert "skill-b" not in prompt_text


def test_modify_request_falls_back_to_full_list_when_relevant_skill_names_is_none():
    """REQ-002 (modified): `relevant_skill_names=None` -> mostra todas as skills.

    A mensagem abaixo só compartilha token com `skill-a` (o antigo filtro por
    token teria excluído `skill-b`); isso garante que o teste discrimina o
    comportamento novo (lê `relevant_skill_names`) do antigo (recalcula via
    token overlap), em vez de acertar por acidente.
    """
    skill_a = _skill("skill-a", "alpha widget description")
    skill_b = _skill("skill-b", "bravo gadget content")
    state = {
        "skills_metadata": [skill_a, skill_b],
        "relevant_skill_names": None,
        "messages": [HumanMessage(content="alpha widget")],
    }

    request = _middleware().modify_request(_request(state))

    prompt_text = request.system_message.text if request.system_message else ""
    assert "skill-a" in prompt_text
    assert "skill-b" in prompt_text


# --- threshold env var override (task-calibration-1) ------------------------


def test_skill_relevance_threshold_reads_env_var_override(monkeypatch):
    """Env var `SKILL_RELEVANCE_THRESHOLD` sobrescreve o default calibrado."""
    monkeypatch.setenv("SKILL_RELEVANCE_THRESHOLD", "0.9")
    assert mod._skill_relevance_threshold() == pytest.approx(0.9)


def test_skill_relevance_threshold_falls_back_to_default_when_unset(monkeypatch):
    """Sem a env var, usa o default calibrado (`_DEFAULT_SKILL_RELEVANCE_THRESHOLD`)."""
    monkeypatch.delenv("SKILL_RELEVANCE_THRESHOLD", raising=False)
    assert mod._skill_relevance_threshold() == pytest.approx(mod._DEFAULT_SKILL_RELEVANCE_THRESHOLD)


def test_modify_request_never_triggers_embedding_computation(monkeypatch):
    """ADDED (delta): `modify_request` só lê o state, nunca computa embeddings."""
    calls = {"sync": 0, "async": 0}
    monkeypatch.setattr(mod, "embed_texts", lambda texts: calls.__setitem__("sync", calls["sync"] + 1) or [[0.0]])
    monkeypatch.setattr(mod, "aembed_texts", lambda texts: calls.__setitem__("async", calls["async"] + 1))

    skill_a = _skill("skill-a", "Skill A description")
    state = {"skills_metadata": [skill_a], "relevant_skill_names": ["skill-a"]}
    middleware = _middleware()

    for _ in range(3):
        middleware.modify_request(_request(state))

    assert calls["sync"] == 0
    assert calls["async"] == 0
