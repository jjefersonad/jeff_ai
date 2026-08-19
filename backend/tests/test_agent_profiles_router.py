"""HTTP POST/PATCH de `mcp_allowlist` em `/api/agent-profiles` (schema-1 / REQ-004)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import src.infrastructure.web.agent_profiles_router as agent_profiles_router
import src.infrastructure.web.webapp as webapp
from src.application.use_cases.create_agent_profile import CreateAgentProfile
from src.application.use_cases.update_agent_profile import UpdateAgentProfile
from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.users import User
from tests.agent_profile_repository_fakes import InMemoryAgentProfileRepository

_USER = User(
    id="user-a",
    username="bob",
    password_hash="h",
    role="user",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
)


@pytest.fixture
def repo() -> InMemoryAgentProfileRepository:
    return InMemoryAgentProfileRepository()


@pytest.fixture
def client(repo: InMemoryAgentProfileRepository):
    webapp.app.dependency_overrides[require_auth] = lambda: _USER
    webapp.app.dependency_overrides[
        agent_profiles_router._create_agent_profile_use_case
    ] = lambda: CreateAgentProfile(repository=repo)
    webapp.app.dependency_overrides[
        agent_profiles_router._update_agent_profile_use_case
    ] = lambda: UpdateAgentProfile(repository=repo)
    try:
        yield TestClient(webapp.app)
    finally:
        webapp.app.dependency_overrides.pop(require_auth, None)
        webapp.app.dependency_overrides.pop(
            agent_profiles_router._create_agent_profile_use_case, None
        )
        webapp.app.dependency_overrides.pop(
            agent_profiles_router._update_agent_profile_use_case, None
        )


def test_post_mcp_allowlist_github_returns_201(client: TestClient) -> None:
    resp = client.post(
        "/api/agent-profiles",
        json={
            "name": "Coder",
            "slug": "coder",
            "system_prompt": "x",
            "mcp_allowlist": ["github"],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["mcp_allowlist"] == ["github"]


def test_patch_mcp_allowlist_github_returns_200(client: TestClient) -> None:
    created = client.post(
        "/api/agent-profiles",
        json={"name": "Coder", "slug": "coder", "system_prompt": "x"},
    )
    assert created.status_code == 201, created.text
    profile_id = created.json()["id"]

    resp = client.patch(
        f"/api/agent-profiles/{profile_id}",
        json={"mcp_allowlist": ["github"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["mcp_allowlist"] == ["github"]
