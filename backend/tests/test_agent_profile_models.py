"""Testes de domínio de `AgentProfile.mcp_allowlist` (schema-1 / REQ-004)."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.domain.agents import AgentProfile
from src.domain.shared.errors import DomainError


def _profile(**overrides: object) -> AgentProfile:
    now = datetime.now(UTC)
    kwargs: dict[str, object] = {
        "id": "p1",
        "user_id": "u1",
        "name": "Coder",
        "slug": "coder",
        "system_prompt": "x",
        "created_at": now,
        "updated_at": now,
    }
    kwargs.update(overrides)
    return AgentProfile(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "mcp_allowlist",
    [None, [], ["github"]],
)
def test_mcp_allowlist_accepts_none_empty_and_names(
    mcp_allowlist: list[str] | None,
) -> None:
    profile = _profile(mcp_allowlist=mcp_allowlist)
    assert profile.mcp_allowlist == mcp_allowlist
    if mcp_allowlist is None:
        assert profile.mcp_allowlist is None


def test_mcp_allowlist_rejects_non_list() -> None:
    with pytest.raises(DomainError, match="mcp_allowlist"):
        _profile(mcp_allowlist="github")


def test_mcp_allowlist_rejects_non_string_items() -> None:
    with pytest.raises(DomainError, match="mcp_allowlist"):
        _profile(mcp_allowlist=[1])
