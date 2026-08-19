"""Stamp server-side de `profile_id` no create_run (runtime-4 / REQ-002).

O cliente sugere; o servidor valida via `GetAgentProfile` com o `user_id`
da sessão. Miss, cross-user ou arquivado recusam com
`Auth.exceptions.HTTPException(400, "profile_id inválido")` — o mesmo
canal nativo de `@auth.on.threads.create_run` que o 401 (confirmado
empiricamente: `Auth.exceptions.HTTPException` aceita `status_code=400`;
FastAPI `HTTPException` não é o mecanismo deste hook). Sem fallback
para `get_default`. Id válido é carimbado em `configurable` e
`metadata.profile_id`, sobrescrevendo o cliente.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Sequence

import pytest
from langgraph_sdk import Auth
from langgraph_sdk.auth import types as auth_types

import src.infrastructure.web.auth as auth_mod
from src.domain.agents import AgentProfile
from src.infrastructure.web.auth import stamp_user_key_on_run_create


@dataclass
class _FakeUser:
    identity: str
    permissions: Sequence[str] = ("user",)
    is_authenticated: bool = True
    display_name: str = "test"


def _auth_ctx(
    identity: str,
    *,
    permissions: Sequence[str] = ("user",),
) -> auth_types.AuthContext:
    user = _FakeUser(identity=identity, permissions=permissions)
    return auth_types.AuthContext(
        user=user,  # type: ignore[arg-type]
        permissions=list(permissions),
        resource="threads",
        action="create_run",
    )


def _run_value(*, profile_id: str | None = None, metadata_profile_id: str | None = "spoof") -> dict:
    configurable: dict = {
        "user_key": "web:spoofed-from-frontend",
        "thread_id": "thread-abc",
    }
    if profile_id is not None:
        configurable["profile_id"] = profile_id
    metadata: dict = {"owner": "spoof-owner"}
    if metadata_profile_id is not None:
        metadata["profile_id"] = metadata_profile_id
    return {
        "metadata": metadata,
        "kwargs": {"config": {"configurable": configurable}},
    }


def _profile(*, profile_id: str, user_id: str, archived: bool = False) -> AgentProfile:
    now = datetime.now(UTC)
    return AgentProfile(
        id=profile_id,
        user_id=user_id,
        name="Coder",
        slug="coder",
        system_prompt="x",
        is_active=not archived,
        archived_at=now if archived else None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_create_run_refuses_another_users_profile_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN o cliente envia o profile_id de outro user THEN recusa e não carimba."""
    identity = "user-a"
    forged = "profile-of-b"

    async def _lookup(user_id: str, profile_id: str) -> AgentProfile | None:
        return None

    monkeypatch.setattr(auth_mod, "_lookup_owned_profile", _lookup, raising=False)

    value = _run_value(profile_id=forged)
    with pytest.raises(Auth.exceptions.HTTPException) as exc_info:
        await stamp_user_key_on_run_create(_auth_ctx(identity), value)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "profile_id inválido"
    configurable = value["kwargs"]["config"]["configurable"]
    assert configurable.get("profile_id") != forged
    assert value["metadata"].get("profile_id") != forged


@pytest.mark.asyncio
async def test_create_run_refuses_archived_profile_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN profile_id aponta para perfil arquivado THEN recusa, sem get_default."""
    identity = "user-a"
    archived_id = "archived-profile"
    get_default_calls = 0

    async def _lookup(user_id: str, profile_id: str) -> AgentProfile | None:
        return _profile(profile_id=archived_id, user_id=identity, archived=True)

    async def _get_default(user_id: str) -> AgentProfile | None:
        nonlocal get_default_calls
        get_default_calls += 1
        return _profile(profile_id="default-id", user_id=identity)

    monkeypatch.setattr(auth_mod, "_lookup_owned_profile", _lookup, raising=False)
    monkeypatch.setattr(auth_mod, "_get_default_profile", _get_default, raising=False)

    value = _run_value(profile_id=archived_id)
    with pytest.raises(Auth.exceptions.HTTPException) as exc_info:
        await stamp_user_key_on_run_create(_auth_ctx(identity), value)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "profile_id inválido"
    assert get_default_calls == 0
    assert value["kwargs"]["config"]["configurable"].get("profile_id") != archived_id


@pytest.mark.asyncio
async def test_create_run_stamps_owned_active_profile_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN o cliente envia um id ativo e próprio THEN carimba UUID em configurable e metadata."""
    identity = "user-a"
    owned_id = "owned-active-profile"
    profile = _profile(profile_id=owned_id, user_id=identity)

    async def _lookup(user_id: str, profile_id: str) -> AgentProfile | None:
        assert user_id == identity
        assert profile_id == owned_id
        return profile

    monkeypatch.setattr(auth_mod, "_lookup_owned_profile", _lookup, raising=False)

    value = _run_value(profile_id=owned_id, metadata_profile_id="forged-metadata")
    await stamp_user_key_on_run_create(_auth_ctx(identity), value)

    configurable = value["kwargs"]["config"]["configurable"]
    assert configurable["profile_id"] == owned_id
    assert value["metadata"]["profile_id"] == owned_id
    assert value["metadata"]["profile_id"] != "forged-metadata"


@pytest.mark.asyncio
async def test_create_run_overwrites_previous_thread_profile_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-006: um novo profile_id no próximo create_run sobrescreve a metadata."""
    identity = "user-a"
    first_id = "profile-one"
    second_id = "profile-two"
    profiles = {
        first_id: _profile(profile_id=first_id, user_id=identity),
        second_id: _profile(profile_id=second_id, user_id=identity),
    }

    async def _lookup(user_id: str, profile_id: str) -> AgentProfile | None:
        return profiles.get(profile_id)

    monkeypatch.setattr(auth_mod, "_lookup_owned_profile", _lookup, raising=False)

    value = _run_value(profile_id=first_id)
    await stamp_user_key_on_run_create(_auth_ctx(identity), value)
    assert value["metadata"]["profile_id"] == first_id

    value["kwargs"]["config"]["configurable"]["profile_id"] = second_id
    await stamp_user_key_on_run_create(_auth_ctx(identity), value)
    assert value["kwargs"]["config"]["configurable"]["profile_id"] == second_id
    assert value["metadata"]["profile_id"] == second_id


@pytest.mark.asyncio
async def test_create_run_omitted_profile_id_is_noop_overlay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Web sem profile_id não chama get_default e não carimba a chave."""
    identity = "user-a"
    lookups = 0
    get_default_calls = 0

    async def _lookup(user_id: str, profile_id: str) -> AgentProfile | None:
        nonlocal lookups
        lookups += 1
        return None

    async def _get_default(user_id: str) -> AgentProfile | None:
        nonlocal get_default_calls
        get_default_calls += 1
        return _profile(profile_id="default-id", user_id=identity)

    monkeypatch.setattr(auth_mod, "_lookup_owned_profile", _lookup, raising=False)
    monkeypatch.setattr(auth_mod, "_get_default_profile", _get_default, raising=False)

    value = _run_value(profile_id=None, metadata_profile_id=None)
    await stamp_user_key_on_run_create(_auth_ctx(identity), value)

    configurable = value["kwargs"]["config"]["configurable"]
    assert "profile_id" not in configurable
    assert "profile_id" not in value["metadata"]
    assert lookups == 0
    assert get_default_calls == 0
