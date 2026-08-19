from datetime import UTC, datetime

import pytest

from src.application.use_cases.update_agent_profile import (
    UpdateAgentProfile,
)
from src.domain.agents import AgentProfile
from src.domain.shared.errors import DomainError
from tests.agent_profile_repository_fakes import (
    InMemoryAgentProfileRepository,
)


@pytest.fixture
def repo() -> InMemoryAgentProfileRepository:
    return InMemoryAgentProfileRepository()


@pytest.fixture
def use_case(
    repo: InMemoryAgentProfileRepository,
) -> UpdateAgentProfile:
    return UpdateAgentProfile(repository=repo)


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


async def test_partial_update_name(
    use_case: UpdateAgentProfile, repo: InMemoryAgentProfileRepository
) -> None:
    seeded = await _seed(repo)
    updated = await use_case.execute(
        user_id="u1", profile_id=seeded.id, name="Renamed"
    )
    assert updated is not None
    assert updated.name == "Renamed"
    assert updated.slug == seeded.slug
    assert updated.system_prompt == seeded.system_prompt


async def test_update_skills_allowlist(
    use_case: UpdateAgentProfile, repo: InMemoryAgentProfileRepository
) -> None:
    seeded = await _seed(repo)
    updated = await use_case.execute(
        user_id="u1", profile_id=seeded.id, skills_allowlist=["pdf", "pptx"]
    )
    assert updated is not None
    assert updated.skills_allowlist == ["pdf", "pptx"]


async def test_update_skills_with_none_clears_it(
    use_case: UpdateAgentProfile, repo: InMemoryAgentProfileRepository
) -> None:
    seeded = await _seed(repo)
    await use_case.execute(
        user_id="u1", profile_id=seeded.id, skills_allowlist=["pdf"]
    )
    updated = await use_case.execute(
        user_id="u1", profile_id=seeded.id, skills_allowlist=None
    )
    assert updated is not None
    assert updated.skills_allowlist is None


async def test_miss_returns_none(
    use_case: UpdateAgentProfile,
) -> None:
    result = await use_case.execute(
        user_id="u1", profile_id="does-not-exist", name="X"
    )
    assert result is None


async def test_cross_user_miss_returns_none(
    use_case: UpdateAgentProfile, repo: InMemoryAgentProfileRepository
) -> None:
    await _seed(repo, user_id="u1")
    result = await use_case.execute(
        user_id="u2", profile_id="p1", name="Hijack"
    )
    assert result is None
    current = await repo.get("u1", "p1")
    assert current is not None
    assert current.name == "Coder"


async def test_empty_name_rejected(
    use_case: UpdateAgentProfile, repo: InMemoryAgentProfileRepository
) -> None:
    seeded = await _seed(repo)
    with pytest.raises(DomainError, match="name"):
        await use_case.execute(
            user_id="u1", profile_id=seeded.id, name="   "
        )
