"""Round-trip Postgres de `AgentProfile.mcp_allowlist` (schema-1 / REQ-004).

WHEN mcp_allowlist is None, [] ou ["github"] THEN create/get devolve o mesmo
valor, sem coercer None para []. Persistência grava o `name` do servidor MCP
como string — não resolve o catálogo de outro `user_id` (REQ-005).

Requer `INTEGRATION_POSTGRES_URI` (mesmo padrão de `test_crm_repository.py`).
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import psycopg
import pytest

from src.domain.agents import AgentProfile
from src.infrastructure.persistence.agent_profile_repository import (
    PostgresAgentProfileRepository,
)
from src.infrastructure.persistence.agent_profiles_schema import (
    ensure_agent_profiles_schema,
)

INTEGRATION_URI_ENV = "INTEGRATION_POSTGRES_URI"
pytestmark = pytest.mark.skipif(
    not os.environ.get(INTEGRATION_URI_ENV),
    reason=(
        f"Requer Postgres de teste real. Defina {INTEGRATION_URI_ENV} "
        "(ex.: postgresql://jeff_ia:jeff_ia@localhost:5436/jeff_ia)."
    ),
)


def _uri() -> str:
    return os.environ[INTEGRATION_URI_ENV]


@pytest.fixture(autouse=True)
def _setup_postgres() -> None:
    ensure_agent_profiles_schema(_uri())
    with psycopg.connect(_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE agent_profiles")
        conn.commit()


def _profile(*, mcp_allowlist: list[str] | None, slug: str) -> AgentProfile:
    now = datetime.now(UTC)
    return AgentProfile(
        id=str(uuid.uuid4()),
        user_id="u-mcp-allowlist",
        name="Coder",
        slug=slug,
        system_prompt="x",
        mcp_allowlist=mcp_allowlist,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.parametrize(
    ("mcp_allowlist", "slug"),
    [
        (None, "coder-none"),
        ([], "coder-empty"),
        (["github"], "coder-github"),
    ],
)
async def test_create_get_round_trips_mcp_allowlist(
    mcp_allowlist: list[str] | None, slug: str
) -> None:
    repo = PostgresAgentProfileRepository(_uri())
    created = await repo.create(_profile(mcp_allowlist=mcp_allowlist, slug=slug))
    got = await repo.get(created.user_id, created.id)

    assert got is not None
    assert got.mcp_allowlist == mcp_allowlist
    if mcp_allowlist is None:
        assert got.mcp_allowlist is None
