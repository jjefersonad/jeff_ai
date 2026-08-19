"""Intersect `skills_allowlist` with the semantic skill filter (skills-1 / REQ-003).

Overlay ativo: `ScopedSkillsMiddleware.modify_request` aplica
semântico ∩ `skills_allowlist`. `None` = sem corte extra; `[]` = nenhuma
listing; a allowlist é teto (não pin).
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from langchain.agents.middleware.types import ModelRequest

from src.agents.unified import scoped_skills_middleware as mod
from src.agents.unified.scoped_skills_middleware import ScopedSkillsMiddleware
from src.domain.agents import AgentProfile


def _skill(name: str, description: str = "") -> dict:
    return {
        "path": f"/skills/{name}/SKILL.md",
        "name": name,
        "description": description or f"{name} skill",
        "license": None,
        "compatibility": None,
        "metadata": {},
        "allowed_tools": [],
    }


def _middleware() -> ScopedSkillsMiddleware:
    return ScopedSkillsMiddleware(backend="dummy-backend", sources=["/skills/"])


def _request(state: dict) -> ModelRequest:
    return ModelRequest(  # type: ignore[arg-type]
        model=None,
        messages=state.get("messages", []),
        state=state,
    )


def _profile(*, skills_allowlist: list[str] | None) -> AgentProfile:
    now = datetime.now(UTC)
    return AgentProfile(
        id="p1",
        user_id="u1",
        name="Marketer",
        slug="marketer",
        system_prompt="x",
        skills_allowlist=skills_allowlist,
        created_at=now,
        updated_at=now,
    )


def _prompt_text(state: dict) -> str:
    request = _middleware().modify_request(_request(state))
    return request.system_message.text if request.system_message else ""


def test_none_allowlist_keeps_semantic_relevant_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """WHEN skills_allowlist is None THEN o conjunto injetado é o semântico de hoje."""
    skill_crm = _skill("crm")
    skill_pdf = _skill("pdf")
    state = {
        "skills_metadata": [skill_crm, skill_pdf],
        "relevant_skill_names": ["crm"],
    }

    without_overlay = _prompt_text(state)

    monkeypatch.setattr(
        mod,
        "get_current_agent_profile",
        lambda: _profile(skills_allowlist=None),
        raising=False,
    )
    with_none_allowlist = _prompt_text(state)

    assert "crm" in without_overlay
    assert "pdf" not in without_overlay
    assert with_none_allowlist == without_overlay


def test_empty_allowlist_injects_no_skill_listing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN skills_allowlist is [] THEN nenhuma skill listing é injetada."""
    skill_crm = _skill("crm")
    skill_pdf = _skill("pdf")
    state = {
        "skills_metadata": [skill_crm, skill_pdf],
        "relevant_skill_names": ["crm", "pdf"],
    }

    monkeypatch.setattr(
        mod,
        "get_current_agent_profile",
        lambda: _profile(skills_allowlist=[]),
        raising=False,
    )

    prompt = _prompt_text(state)
    assert "crm" not in prompt
    assert "pdf" not in prompt


def test_allowlist_does_not_pin_skill_that_failed_semantic_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN a skill está na allowlist mas falha o limiar semântico THEN é omitida."""
    skill_crm = _skill("crm")
    skill_pdf = _skill("pdf")
    state = {
        "skills_metadata": [skill_crm, skill_pdf],
        "relevant_skill_names": ["crm"],
    }

    monkeypatch.setattr(
        mod,
        "get_current_agent_profile",
        lambda: _profile(skills_allowlist=["crm", "pdf"]),
        raising=False,
    )

    prompt = _prompt_text(state)
    assert "crm" in prompt
    assert "pdf" not in prompt


def test_named_allowlist_intersects_semantic_relevant_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN allowlist is [crm, pdf] and only crm is relevant THEN only crm is injected."""
    skill_crm = _skill("crm")
    skill_pdf = _skill("pdf")
    skill_email = _skill("email")
    state = {
        "skills_metadata": [skill_crm, skill_pdf, skill_email],
        "relevant_skill_names": ["crm", "email"],
    }

    monkeypatch.setattr(
        mod,
        "get_current_agent_profile",
        lambda: _profile(skills_allowlist=["crm", "pdf"]),
        raising=False,
    )

    prompt = _prompt_text(state)
    assert "crm" in prompt
    assert "pdf" not in prompt
    assert "email" not in prompt


def test_fail_open_semantic_still_intersects_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Overlay ativo: `relevant_skill_names is None` (fail-open) ainda aplica o teto."""
    state = {
        "skills_metadata": [_skill("crm"), _skill("email")],
        "relevant_skill_names": None,
    }
    monkeypatch.setattr(
        mod,
        "get_current_agent_profile",
        lambda: _profile(skills_allowlist=["crm"]),
        raising=False,
    )
    prompt = _prompt_text(state)
    assert "crm" in prompt
    assert "email" not in prompt
