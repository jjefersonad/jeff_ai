from datetime import UTC, datetime

import pytest

from src.application.use_cases.list_agent_profiles import (
    ListAgentProfiles,
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
) -> ListAgentProfiles:
    return ListAgentProfiles(repository=repo)


async def _seed(
    repo: InMemoryAgentProfileRepository, user_id: str, slug: str
) -> AgentProfile:
    now = datetime.now(UTC)
    p = AgentProfile(
        id=f"{user_id}-{slug}",
        user_id=user_id,
        name=slug,
        slug=slug,
        system_prompt="x",
        created_at=now,
        updated_at=now,
    )
    await repo.create(p)
    return p


async def test_lists_only_active_by_default(
    use_case: ListAgentProfiles, repo: InMemoryAgentProfileRepository
) -> None:
    await _seed(repo, "u1", "coder")
    await _seed(repo, "u1", "researcher")
    await repo.archive("u1", "u1-researcher")
    items = await use_case.execute(user_id="u1")
    assert [p.slug for p in items] == ["coder"]


async def test_include_archived_returns_all(
    use_case: ListAgentProfiles, repo: InMemoryAgentProfileRepository
) -> None:
    await _seed(repo, "u1", "coder")
    await _seed(repo, "u1", "researcher")
    await repo.archive("u1", "u1-researcher")
    items = await use_case.execute(user_id="u1", include_archived=True)
    assert {p.slug for p in items} == {"coder", "researcher"}


async def test_isolates_per_user(
    use_case: ListAgentProfiles, repo: InMemoryAgentProfileRepository
) -> None:
    await _seed(repo, "u1", "coder")
    await _seed(repo, "u2", "coder")
    u1 = await use_case.execute(user_id="u1")
    u2 = await use_case.execute(user_id="u2")
    assert len(u1) == 1 and u1[0].user_id == "u1"
    assert len(u2) == 1 and u2[0].user_id == "u2"


async def test_empty_list_for_unknown_user(
    use_case: ListAgentProfiles,
) -> None:
    assert await use_case.execute(user_id="nobody") == []
