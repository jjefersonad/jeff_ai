"""Testes de carimbo server-side de `user_key` web no create_run (recording-3).

Unit: auth/web carimba web user_key
- WHEN um hook/handler de create-run autentica um usuário com identity UUID
- THEN o configurable (ou valor efetivo resolvido pelo gravador) usa
  `web:<uuid>` e ignora user_key arbitrário do cliente se presente
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import pytest
from langgraph_sdk.auth import types as auth_types

from src.infrastructure.usage.user_key import web_user_key
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


@pytest.mark.asyncio
async def test_create_run_stamps_web_user_key_and_ignores_client() -> None:
    """REQ-002/REQ-003: identity UUID → web:<uuid>; cliente spoofado é sobrescrito."""
    identity = "550e8400-e29b-41d4-a716-446655440000"
    value: dict = {
        "metadata": {},
        "kwargs": {
            "config": {
                "configurable": {
                    "user_key": "web:spoofed-from-frontend",
                    "thread_id": "thread-abc",
                },
                "recursion_limit": 100,
            }
        },
    }

    result = await stamp_user_key_on_run_create(_auth_ctx(identity), value)

    expected = web_user_key(identity)
    assert expected == f"web:{identity}"
    configurable = value["kwargs"]["config"]["configurable"]
    assert configurable["user_key"] == expected
    assert configurable["user_key"] != "web:spoofed-from-frontend"
    assert value["metadata"]["owner"] == identity
    # Não-admin continua filtrado por owner (mesmo contrato do @auth.on global).
    assert result == {"owner": identity}


@pytest.mark.asyncio
async def test_create_run_stamps_user_key_even_for_admin() -> None:
    """Admin também recebe user_key server-side (bypass de filtro ≠ sem identidade)."""
    identity = "admin-user-id"
    value: dict = {"kwargs": {"config": {"configurable": {}}}}

    result = await stamp_user_key_on_run_create(
        _auth_ctx(identity, permissions=("admin",)),
        value,
    )

    assert value["kwargs"]["config"]["configurable"]["user_key"] == web_user_key(
        identity
    )
    assert result == {}
