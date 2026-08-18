from datetime import UTC, datetime

import pytest

from src.application.use_cases.get_agent_profile import (
    GetAgentProfile,
)
from src.domain.agents import AgentProfile
from tests.agent_profile_repository_fakes import (
    InMemoryAgentProfileRepository,
)


@pytest.fixture
def repo() -> InMemoryAgentProfileRepository:
    return InMemoryAgentProfileRepository()


@pytest.fixture
def use_case(
    repo: InMemoryAgentProfileRepository,
) -> GetAgentProfile:
    return GetAgentProfile(repository=repo)


async def _seed(
    repo: InMemoryAgentProfileRepository, user_id: str = "u1"
) -> AgentProfile:
    now = datetime.now(UTC)
    p = AgentProfile(
        id="p1",
        user_id=user_id,
        name="Coder",
        slug="coder",
        system_prompt="x",
        created_at=now,
        updated_at=now,
    )
    await repo.create(p)
    return p


async def test_returns_own_profile(
    use_case: GetAgentProfile, repo: InMemoryAgentProfileRepository
) -> None:
    seeded = await _seed(repo)
    got = await use_case.execute(user_id="u1", profile_id=seeded.id)
    assert got is not None
    assert got.id == seeded.id


async def test_cross_user_returns_none(
    use_case: GetAgentProfile, repo: InMemoryAgentProfileRepository
) -> None:
    await _seed(repo, user_id="u1")
    got = await use_case.execute(user_id="u2", profile_id="p1")
    assert got is None


async def test_unknown_returns_none(use_case: GetAgentProfile) -> None:
    assert await use_case.execute(user_id="u1", profile_id="x") is None
