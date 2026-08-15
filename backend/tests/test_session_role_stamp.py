"""session-file-sandbox identity: carimbo server-side de configurable.role."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import pytest
from langgraph_sdk.auth import types as auth_types

from src.infrastructure.agent_runtime.langgraph_direct_runner import _build_run_config
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
async def test_create_run_stamps_role_from_session_and_ignores_client_spoof() -> None:
    """REQ-001: permissions [user] ⇒ role=user even if client sent admin."""
    identity = "550e8400-e29b-41d4-a716-446655440000"
    value: dict = {
        "metadata": {},
        "kwargs": {
            "config": {
                "configurable": {
                    "user_key": "web:spoofed",
                    "role": "admin",
                    "thread_id": "thread-abc",
                },
            }
        },
    }

    await stamp_user_key_on_run_create(_auth_ctx(identity, permissions=("user",)), value)

    configurable = value["kwargs"]["config"]["configurable"]
    assert configurable["role"] == "user"
    assert configurable["role"] != "admin"


def test_build_run_config_defaults_role_to_user_when_unresolved() -> None:
    """REQ-001: identidade ausente ⇒ role=user (nunca admin por omissão)."""
    config = _build_run_config(thread_id="t1", user_key=None)
    assert config["configurable"]["role"] == "user"

    config_unknown = _build_run_config(thread_id="t1", user_key="unknown")
    assert config_unknown["configurable"]["role"] == "user"
