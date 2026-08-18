from datetime import UTC, datetime

import pytest

from src.application.use_cases.archive_agent_profile import (
    ArchiveAgentProfile,
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
) -> ArchiveAgentProfile:
    return ArchiveAgentProfile(repository=repo)


async def test_archive_soft_deletes(
    use_case: ArchiveAgentProfile, repo: InMemoryAgentProfileRepository
) -> None:
    p = AgentProfile(
        id="p1",
        user_id="u1",
        name="Coder",
        slug="coder",
        system_prompt="x",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await repo.create(p)
    archived = await use_case.execute(user_id="u1", profile_id="p1")
    assert archived is not None
    assert archived.is_active is False
    assert archived.archived_at is not None


async def test_miss_returns_none(
    use_case: ArchiveAgentProfile,
) -> None:
    assert await use_case.execute(user_id="u1", profile_id="x") is None


async def test_cross_user_returns_none(
    use_case: ArchiveAgentProfile, repo: InMemoryAgentProfileRepository
) -> None:
    await repo.create(
        AgentProfile(
            id="p1",
            user_id="u1",
            name="Coder",
            slug="coder",
            system_prompt="x",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    assert await use_case.execute(user_id="u2", profile_id="p1") is None
    assert (await repo.get("u1", "p1")).is_active is True
