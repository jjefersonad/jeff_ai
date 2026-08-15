"""user-project-skills-layers middleware-1: dual ScopedSkillsMiddleware sources."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from src.agents.unified import agent as agent_mod
from src.agents.unified import scoped_skills_middleware as scoped_mod
from src.agents.unified.agent import build_unified
from src.agents.unified.scoped_skills_middleware import ScopedSkillsMiddleware
from src.infrastructure.ownership.paths import user_skills_root


class _FakeCompiledGraph:
    def with_config(self, _config: Any) -> _FakeCompiledGraph:
        return self


def _call_build_unified_and_capture_kwargs() -> dict[str, Any]:
    with patch.object(
        agent_mod, "create_deep_agent", side_effect=lambda **_kwargs: _FakeCompiledGraph()
    ) as spy:
        build_unified()
        return spy.call_args.kwargs


def _patch_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    dirs = {
        "WORKSPACE_DIR": tmp_path / "workspace",
        "REPO_ROOT": tmp_path / "repo",
        "OUTPUTS_DIR": tmp_path / "outputs",
        "SPECIFY_DIR": tmp_path / "specify",
        "TEMPLATES_DIR": tmp_path / "templates",
        "SKILLS_DIR": tmp_path / "skills",
    }
    for name, path in dirs.items():
        path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(agent_mod, name, path)
    monkeypatch.setenv("FILES_DIR", str(tmp_path / "files"))
    (tmp_path / "files").mkdir(parents=True, exist_ok=True)
    return dirs


def _write_skill(root: Path, name: str, description: str | None = None) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    desc = description or f"{name} skill for tests"
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n# {name}\n",
        encoding="utf-8",
    )


class _FailClosedDefaultBackend:
    """Stand-in for StateBackend outside a LangGraph run.

    When `/user-skills/` is not mounted, CompositeBackend falls through to the
    default. In production that is StateBackend (empty / error). Outside a graph
    StateBackend raises; this stub returns a recoverable ls error so D1
    fail-closed still loads the project layer.
    """

    def ls(self, path: str) -> Any:
        from deepagents.backends.protocol import LsResult

        return LsResult(error=f"Path not routed: {path}", entries=[])

    def download_files(self, paths: list[str]) -> list[Any]:
        from deepagents.backends.protocol import FileDownloadResponse

        return [FileDownloadResponse(path=p, content=None, error="not found") for p in paths]


def _backend_for(
    *,
    role: str,
    thread_id: str = "thread-1",
    user_key: str | None = "web:user-a",
    user_id: str | None = None,
) -> Any:
    configurable: dict[str, Any] = {"thread_id": thread_id, "role": role}
    if user_key is not None:
        configurable["user_key"] = user_key
    if user_id is not None:
        configurable["user_id"] = user_id
    with patch(
        "src.composition.backends.get_config",
        return_value={"configurable": configurable},
    ):
        backend = agent_mod._build_backend_factory()(MagicMock())
    # Avoid StateBackend RuntimeError when an unmounted source is probed.
    backend.default = _FailClosedDefaultBackend()
    return backend


def _production_skills_middleware(backend: Any) -> ScopedSkillsMiddleware:
    """Mirror production sources (must stay in sync with build_unified)."""
    kwargs = _call_build_unified_and_capture_kwargs()
    prod = next(m for m in kwargs["middleware"] if isinstance(m, ScopedSkillsMiddleware))
    return ScopedSkillsMiddleware(
        backend=backend,
        sources=list(zip(prod.sources, prod.source_labels, strict=True)),
    )


def _load_skills_metadata(
    middleware: ScopedSkillsMiddleware, monkeypatch: pytest.MonkeyPatch
) -> list[dict]:
    """Run before_agent with embeddings stubbed; return skills_metadata."""

    def _fake_embed(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr(scoped_mod, "embed_texts", _fake_embed)
    state: dict[str, Any] = {"messages": [HumanMessage(content="hello")]}
    update = middleware.before_agent(state, runtime=MagicMock(), config={})
    assert update is not None
    return list(update["skills_metadata"])


def _names(skills: list[dict]) -> set[str]:
    return {s["name"] for s in skills}


def _by_name(skills: list[dict], name: str) -> dict:
    matches = [s for s in skills if s["name"] == name]
    assert len(matches) == 1, f"expected exactly one {name!r}, got {matches!r}"
    return matches[0]


# --- middleware-1 unit-1 (REQ-001 scenario 1) --------------------------------


def test_both_layers_contribute_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN project has pdf and user A has my-crm THEN metadata includes both."""
    dirs = _patch_dirs(tmp_path, monkeypatch)
    _write_skill(dirs["SKILLS_DIR"], "pdf", "project pdf skill")
    _write_skill(user_skills_root("user-a"), "my-crm", "owned crm skill")

    backend = _backend_for(role="user", user_key="web:user-a")
    mw = _production_skills_middleware(backend)
    skills = _load_skills_metadata(mw, monkeypatch)

    assert {"pdf", "my-crm"} <= _names(skills)


# --- middleware-1 unit-2 (REQ-001 scenario 2) --------------------------------


def test_no_user_id_loads_project_layer_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN no resolvable user_id THEN project skills load; no user-owned."""
    dirs = _patch_dirs(tmp_path, monkeypatch)
    _write_skill(dirs["SKILLS_DIR"], "pdf", "project pdf skill")
    # Owned skill for some user must not leak without identity.
    _write_skill(user_skills_root("user-a"), "my-crm", "owned crm skill")

    backend = _backend_for(role="user", user_key=None)
    mw = _production_skills_middleware(backend)
    skills = _load_skills_metadata(mw, monkeypatch)

    assert "pdf" in _names(skills)
    assert "my-crm" not in _names(skills)
    assert all(not str(s.get("path", "")).startswith("/user-skills/") for s in skills)


# --- middleware-1 unit-3 (REQ-001 scenario 3) --------------------------------


def test_empty_user_tree_still_loads_project_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN user A has empty/missing skills dir THEN project skills still load."""
    dirs = _patch_dirs(tmp_path, monkeypatch)
    _write_skill(dirs["SKILLS_DIR"], "pdf", "project pdf skill")
    # Do not create files/user-a/skills/ contents (mount may mkdir empty).

    backend = _backend_for(role="user", user_key="web:user-a")
    mw = _production_skills_middleware(backend)
    skills = _load_skills_metadata(mw, monkeypatch)

    assert "pdf" in _names(skills)


# --- middleware-1 unit-4 (REQ-002 scenario 1 / D1 D2) ------------------------


def test_same_name_user_wins_over_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN both layers define frontmatter name pdf THEN user wins; one entry."""
    dirs = _patch_dirs(tmp_path, monkeypatch)
    _write_skill(dirs["SKILLS_DIR"], "pdf", "project pdf description")
    _write_skill(user_skills_root("user-a"), "pdf", "user owned pdf description")

    backend = _backend_for(role="user", user_key="web:user-a")
    mw = _production_skills_middleware(backend)
    skills = _load_skills_metadata(mw, monkeypatch)

    pdf = _by_name(skills, "pdf")
    assert pdf["description"] == "user owned pdf description"
    assert str(pdf["path"]).startswith("/user-skills/")
    assert sum(1 for s in skills if s["name"] == "pdf") == 1


# --- middleware-1 unit-5 (REQ-002 scenario 2) --------------------------------


def test_distinct_names_both_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN project has xlsx and user has invoice-helper THEN both appear."""
    dirs = _patch_dirs(tmp_path, monkeypatch)
    _write_skill(dirs["SKILLS_DIR"], "xlsx", "spreadsheet skill")
    _write_skill(user_skills_root("user-a"), "invoice-helper", "invoice helper skill")

    backend = _backend_for(role="user", user_key="web:user-a")
    mw = _production_skills_middleware(backend)
    skills = _load_skills_metadata(mw, monkeypatch)

    assert {"xlsx", "invoice-helper"} <= _names(skills)


# --- middleware-1 unit-6 (REQ-002 scenario 3) --------------------------------


def test_other_user_skill_never_shadows_project_for_a(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN B owns pdf but session is A without owned pdf THEN A's pdf is project."""
    dirs = _patch_dirs(tmp_path, monkeypatch)
    _write_skill(dirs["SKILLS_DIR"], "pdf", "project pdf description")
    _write_skill(user_skills_root("user-b"), "pdf", "user B owned pdf")

    backend = _backend_for(role="user", user_key="web:user-a")
    mw = _production_skills_middleware(backend)
    skills = _load_skills_metadata(mw, monkeypatch)

    pdf = _by_name(skills, "pdf")
    assert pdf["description"] == "project pdf description"
    assert str(pdf["path"]).startswith("/skills/")


# --- middleware-1 unit-7 (REQ-005 scenario 1) --------------------------------


def test_admin_with_owned_tree_merges_user_over_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN admin user_id=A and both layers have skills THEN user-over-project."""
    dirs = _patch_dirs(tmp_path, monkeypatch)
    _write_skill(dirs["SKILLS_DIR"], "pdf", "project pdf description")
    _write_skill(user_skills_root("user-a"), "pdf", "admin owned pdf description")
    _write_skill(user_skills_root("user-a"), "my-crm", "admin owned crm")

    backend = _backend_for(role="admin", user_key="web:user-a")
    mw = _production_skills_middleware(backend)
    skills = _load_skills_metadata(mw, monkeypatch)

    pdf = _by_name(skills, "pdf")
    assert pdf["description"] == "admin owned pdf description"
    assert str(pdf["path"]).startswith("/user-skills/")
    assert "my-crm" in _names(skills)


# --- middleware-1 unit-8 (REQ-005 scenario 2) --------------------------------


def test_admin_without_user_layer_loads_project_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN admin has no owned skills root THEN project-default skills still load."""
    dirs = _patch_dirs(tmp_path, monkeypatch)
    _write_skill(dirs["SKILLS_DIR"], "pdf", "project pdf skill")
    _write_skill(user_skills_root("user-a"), "my-crm", "someone else owned")

    backend = _backend_for(role="admin", user_key=None)
    mw = _production_skills_middleware(backend)
    skills = _load_skills_metadata(mw, monkeypatch)

    assert "pdf" in _names(skills)
    assert "my-crm" not in _names(skills)


# --- wiring: Project then User (D1) -----------------------------------------


def test_build_unified_configures_project_then_user_skill_sources() -> None:
    """D1: sources order is /skills/ (Project) then /user-skills/ (User)."""
    kwargs = _call_build_unified_and_capture_kwargs()
    mw = next(m for m in kwargs["middleware"] if isinstance(m, ScopedSkillsMiddleware))
    assert mw.sources == ["/skills/", "/user-skills/"]
    assert mw.source_labels == ["Project", "User"]


# --- middleware-2 unit-1 (REQ-003 / D7) --------------------------------------


def test_relevance_filter_sees_post_merge_user_owned_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN relevance selects a subset THEN it uses collision-resolved merged metadata."""
    dirs = _patch_dirs(tmp_path, monkeypatch)
    _write_skill(dirs["SKILLS_DIR"], "pdf", "project generic document tooling")
    _write_skill(
        user_skills_root("user-a"),
        "pdf",
        "UNIQUE_USER_PDF_OVERLAY_TOKEN custom invoice pdf overlays",
    )
    _write_skill(dirs["SKILLS_DIR"], "xlsx", "spreadsheet grid formulas")

    backend = _backend_for(role="user", user_key="web:user-a")
    mw = _production_skills_middleware(backend)

    def fake_embed(texts: list[str]) -> list[list[float]]:
        text = texts[0].lower()
        # Conversation and user-overlay skill share the unique token vector.
        if "unique_user_pdf_overlay_token" in text:
            return [[1.0, 0.0, 0.0]]
        if "spreadsheet" in text or "xlsx" in text:
            return [[0.0, 1.0, 0.0]]
        if "project generic" in text:
            return [[0.0, 0.0, 1.0]]
        # Human message
        return [[1.0, 0.0, 0.0]]

    monkeypatch.setattr(scoped_mod, "embed_texts", fake_embed)
    scoped_mod._skill_embedding_cache.clear()

    state: dict[str, Any] = {
        "messages": [
            HumanMessage(content="please use UNIQUE_USER_PDF_OVERLAY_TOKEN for invoices")
        ]
    }
    update = mw.before_agent(state, runtime=MagicMock(), config={})
    assert update is not None
    skills = list(update["skills_metadata"])
    pdf = _by_name(skills, "pdf")
    assert pdf["description"].startswith("UNIQUE_USER_PDF_OVERLAY_TOKEN")
    assert sum(1 for s in skills if s["name"] == "pdf") == 1

    relevant = update.get("relevant_skill_names")
    assert relevant is not None
    assert "pdf" in relevant
    # Post-merge filter only — no second source-aware API on the middleware.
    assert not hasattr(mw, "filter_by_source")
    assert not hasattr(mw, "relevant_skills_by_layer")


# --- middleware-2 unit-2 (REQ-003 full-body not reintroduced) ----------------


def test_scoped_injection_lists_name_description_not_full_bodies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN many skills exist across layers THEN prompt lists name/description only."""
    from langchain.agents.middleware.types import ModelRequest

    dirs = _patch_dirs(tmp_path, monkeypatch)
    body_marker = "FULL_BODY_SECRET_MARKER_SHOULD_NOT_APPEAR_IN_PROMPT"
    for i in range(4):
        name = f"proj-skill-{i}"
        skill_dir = dirs["SKILLS_DIR"] / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: project skill {i} listing\n---\n"
            f"# {name}\n{body_marker}\n",
            encoding="utf-8",
        )
    for i in range(3):
        name = f"user-skill-{i}"
        skill_dir = user_skills_root("user-a") / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: user skill {i} listing\n---\n"
            f"# {name}\n{body_marker}\n",
            encoding="utf-8",
        )

    backend = _backend_for(role="user", user_key="web:user-a")
    mw = _production_skills_middleware(backend)
    skills = _load_skills_metadata(mw, monkeypatch)
    assert len(skills) >= 7

    state = {
        "skills_metadata": skills,
        "relevant_skill_names": None,  # fail-open: list all metadata entries
        "messages": [],
    }
    request = mw.modify_request(
        ModelRequest(model=None, messages=[], state=state)  # type: ignore[arg-type]
    )
    prompt_text = request.system_message.text if request.system_message else ""
    assert "proj-skill-0" in prompt_text
    assert "user-skill-0" in prompt_text
    assert "project skill 0 listing" in prompt_text
    assert body_marker not in prompt_text


# --- middleware-2 unit-3 (REQ-004 / D9) --------------------------------------


def test_new_user_skill_eligible_on_later_load_without_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN new skill is created then skills_metadata cleared THEN it loads (no restart)."""
    dirs = _patch_dirs(tmp_path, monkeypatch)
    _write_skill(dirs["SKILLS_DIR"], "pdf", "project pdf skill")

    backend = _backend_for(role="user", user_key="web:user-a")
    mw = _production_skills_middleware(backend)

    first = _load_skills_metadata(mw, monkeypatch)
    assert "new-skill" not in _names(first)

    _write_skill(user_skills_root("user-a"), "new-skill", "brand new user skill")
    # Same process, fresh state (absent skills_metadata) — deepagents once-per-session.
    second = _load_skills_metadata(mw, monkeypatch)
    assert "new-skill" in _names(second)
    assert "pdf" in _names(second)


# --- middleware-2 unit-4 (user-owned-skills REQ-005) -------------------------


def test_user_skill_survives_new_thread_same_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN skill installed in T1 THEN still on disk and loadable in T2 for same user."""
    dirs = _patch_dirs(tmp_path, monkeypatch)
    _write_skill(dirs["SKILLS_DIR"], "pdf", "project pdf skill")
    _write_skill(user_skills_root("user-a"), "durable-skill", "persists across threads")

    owned = user_skills_root("user-a") / "durable-skill" / "SKILL.md"
    assert owned.is_file()

    backend_t1 = _backend_for(role="user", user_key="web:user-a", thread_id="thread-T1")
    mw_t1 = _production_skills_middleware(backend_t1)
    skills_t1 = _load_skills_metadata(mw_t1, monkeypatch)
    assert "durable-skill" in _names(skills_t1)

    # New thread, same user_id — durable path still exists and loads.
    assert owned.is_file()
    backend_t2 = _backend_for(role="user", user_key="web:user-a", thread_id="thread-T2")
    mw_t2 = _production_skills_middleware(backend_t2)
    skills_t2 = _load_skills_metadata(mw_t2, monkeypatch)
    assert "durable-skill" in _names(skills_t2)
    assert str(_by_name(skills_t2, "durable-skill")["path"]).startswith("/user-skills/")
