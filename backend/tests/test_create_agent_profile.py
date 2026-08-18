import pytest

from src.application.use_cases.create_agent_profile import (
    CreateAgentProfile,
)
from src.domain.agents import DuplicateAgentProfileError
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
) -> CreateAgentProfile:
    return CreateAgentProfile(repository=repo)


async def test_creates_profile_with_valid_data(
    use_case: CreateAgentProfile,
    repo: InMemoryAgentProfileRepository,
) -> None:
    profile = await use_case.execute(
        user_id="u1",
        name="Coder",
        slug="coder",
        system_prompt="You are a coding assistant.",
    )
    assert profile.id
    assert profile.user_id == "u1"
    assert profile.name == "Coder"
    assert profile.slug == "coder"
    assert profile.is_active is True
    assert profile.archived_at is None
    assert profile.tier == 1
    assert profile.created_at == profile.updated_at
    stored = await repo.get("u1", profile.id)
    assert stored is not None


async def test_rejects_empty_name(use_case: CreateAgentProfile) -> None:
    with pytest.raises(DomainError, match="name"):
        await use_case.execute(
            user_id="u1",
            name="",
            slug="coder",
            system_prompt="x",
        )


async def test_rejects_whitespace_name(use_case: CreateAgentProfile) -> None:
    with pytest.raises(DomainError, match="name"):
        await use_case.execute(
            user_id="u1",
            name="   ",
            slug="coder",
            system_prompt="x",
        )


async def test_rejects_empty_system_prompt(
    use_case: CreateAgentProfile,
) -> None:
    with pytest.raises(DomainError, match="system_prompt"):
        await use_case.execute(
            user_id="u1",
            name="Coder",
            slug="coder",
            system_prompt="",
        )


async def test_rejects_invalid_slug(use_case: CreateAgentProfile) -> None:
    with pytest.raises(DomainError, match="slug"):
        await use_case.execute(
            user_id="u1",
            name="Coder",
            slug="Coder Agent",
            system_prompt="x",
        )


async def test_rejects_tier_out_of_range(use_case: CreateAgentProfile) -> None:
    with pytest.raises(DomainError, match="tier"):
        await use_case.execute(
            user_id="u1",
            name="Coder",
            slug="coder",
            system_prompt="x",
            tier=5,
        )


async def test_rejects_duplicate_slug(
    use_case: CreateAgentProfile,
) -> None:
    await use_case.execute(
        user_id="u1",
        name="Coder",
        slug="coder",
        system_prompt="x",
    )
    with pytest.raises(DuplicateAgentProfileError):
        await use_case.execute(
            user_id="u1",
            name="Coder 2",
            slug="coder",
            system_prompt="y",
        )


async def test_same_slug_allowed_for_different_users(
    use_case: CreateAgentProfile,
) -> None:
    a = await use_case.execute(
        user_id="u1",
        name="Coder",
        slug="coder",
        system_prompt="x",
    )
    b = await use_case.execute(
        user_id="u2",
        name="Coder",
        slug="coder",
        system_prompt="y",
    )
    assert a.id != b.id
