"""Namespace de memória por perfil (memory-1 / agent-memory REQ-001).

Overlay validado: `("memories", user_id, profile_id)`. Sem overlay:
`("memories", user_id)`. Chat e scheduled run do mesmo par compartilham
o namespace — ambos passam por `_resolve_namespace`.
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from langgraph.store.memory import InMemoryStore

import src.tools.memory_tools as mt
from src.domain.agents import AgentProfile

_USER_ID = "user-a"
_PROFILE_ID = "profile-coder"
_LEGACY_NS = (*mt.MEMORY_NAMESPACE, _USER_ID)
_PROFILE_NS = (*mt.MEMORY_NAMESPACE, _USER_ID, _PROFILE_ID)


def _items_in(store: InMemoryStore, ns: tuple[str, ...]) -> list:
    """`store.search` é prefix-match; isto restringe ao namespace exato."""
    return [item for item in store.search(ns) if tuple(item.namespace) == ns]


def _profile(*, profile_id: str = _PROFILE_ID, user_id: str = _USER_ID) -> AgentProfile:
    now = datetime.now(UTC)
    return AgentProfile(
        id=profile_id,
        user_id=user_id,
        name="Coder",
        slug="coder",
        system_prompt="x",
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> InMemoryStore:
    s = InMemoryStore()
    monkeypatch.setattr(mt, "get_store", lambda: s)
    monkeypatch.setattr(mt, "resolve_user_id", AsyncMock(return_value=_USER_ID))
    return s


@pytest.mark.asyncio
async def test_absent_profile_keeps_legacy_namespace(store: InMemoryStore) -> None:
    """WHEN profile_id is absent THEN namespace is (memories, user_id)."""
    ns = await mt._resolve_namespace()
    assert ns == _LEGACY_NS

    await mt.save_memory.ainvoke({"content": "fato legado"})
    assert any(
        item.value["content"] == "fato legado" for item in _items_in(store, _LEGACY_NS)
    )
    assert _items_in(store, _PROFILE_NS) == []


@pytest.mark.asyncio
async def test_validated_profile_uses_profile_namespace(
    store: InMemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN profile_id is validated THEN namespace is (memories, user_id, profile_id)."""
    monkeypatch.setattr(
        mt, "get_current_agent_profile", lambda: _profile(), raising=False
    )

    ns = await mt._resolve_namespace()
    assert ns == _PROFILE_NS

    await mt.save_memory.ainvoke({"content": "fato do coder"})
    assert any(
        item.value["content"] == "fato do coder"
        for item in _items_in(store, _PROFILE_NS)
    )
    assert _items_in(store, _LEGACY_NS) == []


@pytest.mark.asyncio
async def test_chat_and_scheduled_share_profile_namespace(
    store: InMemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Chat e scheduled run do mesmo owner+profile leem/escrevem o mesmo ns."""
    monkeypatch.setattr(
        mt, "get_current_agent_profile", lambda: _profile(), raising=False
    )

    await mt.save_memory.ainvoke({"content": "preferência salva no chat"})
    out = await mt.search_memory.ainvoke({"query": "preferência"})
    listed = await mt.list_memories.ainvoke({})

    assert "preferência salva no chat" in out
    assert "preferência salva no chat" in listed
    assert await mt._resolve_namespace() == _PROFILE_NS


@pytest.mark.asyncio
async def test_profile_search_excludes_legacy_and_other_user(
    store: InMemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN searching under a profile THEN legado e outro user_id não aparecem."""
    await store.aput(
        _LEGACY_NS,
        "legacy",
        {"content": "fato legado do user-a", "kind": "semantic"},
    )
    await store.aput(
        (*mt.MEMORY_NAMESPACE, "user-b", _PROFILE_ID),
        "other",
        {"content": "segredo do user-b", "kind": "semantic"},
    )
    await store.aput(
        _PROFILE_NS,
        "mine",
        {"content": "fato do perfil coder", "kind": "semantic"},
    )
    monkeypatch.setattr(
        mt, "get_current_agent_profile", lambda: _profile(), raising=False
    )

    out = await mt.search_memory.ainvoke({"query": "fato"})
    listed = await mt.list_memories.ainvoke({})

    assert "fato do perfil coder" in out
    assert "fato legado" not in out
    assert "segredo do user-b" not in out
    assert "fato do perfil coder" in listed
    assert "fato legado" not in listed
    assert "segredo do user-b" not in listed


@pytest.mark.asyncio
async def test_legacy_search_does_not_return_profile_children(
    store: InMemoryStore,
) -> None:
    """Sem overlay, search no legado não devolve itens de perfil (prefix leak)."""
    await store.aput(
        _PROFILE_NS,
        "p",
        {"content": "só do coder", "kind": "semantic"},
    )
    await store.aput(
        _LEGACY_NS,
        "l",
        {"content": "legado visível", "kind": "semantic"},
    )

    out = await mt.search_memory.ainvoke({"query": "coder"})
    listed = await mt.list_memories.ainvoke({})

    assert "legado visível" in out
    assert "só do coder" not in out
    assert "legado visível" in listed
    assert "só do coder" not in listed
