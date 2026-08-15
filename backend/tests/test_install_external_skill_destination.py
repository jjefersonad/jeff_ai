"""user-project-skills-layers task-install-1: role-based install destination (D4/D6)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import src.tools.self_extension as se
from src.infrastructure.ownership.paths import user_skills_root


def _fake_npx_install(skill: str):
    """Plant a SKILL.md under cwd so install_external_skill's walk finds it."""

    def _run(cmd, *, cwd=None, **_kwargs):  # noqa: ANN001, ARG001
        assert cwd is not None
        planted = Path(cwd) / ".agents" / "skills" / skill
        planted.mkdir(parents=True)
        (planted / "SKILL.md").write_text(
            f"---\nname: {skill}\ndescription: test\n---\nbody\n",
            encoding="utf-8",
        )
        return MagicMock(returncode=0, stdout="ok", stderr="")

    return _run


def _cfg(
    *,
    role: str,
    user_key: str | None = "web:user-a",
    user_id: str | None = None,
) -> dict:
    configurable: dict = {"role": role, "thread_id": "t1"}
    if user_key is not None:
        configurable["user_key"] = user_key
    if user_id is not None:
        configurable["user_id"] = user_id
    return {"configurable": configurable}


def _install(
    *,
    repo: str = "vercel-labs/skills",
    skill: str = "find-skills",
    for_user_id: str | None = None,
    role: str = "user",
    user_key: str | None = "web:user-a",
) -> str:
    cfg = _cfg(role=role, user_key=user_key)
    payload: dict = {"repo": repo, "skill": skill}
    if for_user_id is not None:
        payload["for_user_id"] = for_user_id
    with (
        patch("src.composition.backends.get_config", return_value=cfg),
        patch("langgraph.config.get_config", return_value=cfg),
        patch.object(se.shutil, "which", return_value="/usr/bin/npx"),
        patch.object(se.subprocess, "run", side_effect=_fake_npx_install(skill)),
    ):
        return se.install_external_skill.invoke(payload)


# --- install-1 unit-1 (skill-authoring REQ-008 / REQ-002) --------------------


def _patch_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    project_skills = tmp_path / "project-skills"
    project_skills.mkdir()
    monkeypatch.setattr(se, "SKILLS_DIR", project_skills)
    monkeypatch.setenv("FILES_DIR", str(tmp_path / "files"))
    (tmp_path / "files").mkdir()
    return project_skills


def test_user_install_lands_in_owned_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN role=user with user_id=A installs THEN files under files/A/skills/."""
    project_skills = _patch_dirs(tmp_path, monkeypatch)

    out = _install(role="user", user_key="web:user-a", skill="find-skills")

    assert "[OK]" in out or "instalada" in out.lower()
    owned = user_skills_root("user-a") / "find-skills" / "SKILL.md"
    assert owned.is_file(), f"expected owned skill; got out={out!r}"
    assert "find-skills" in owned.read_text(encoding="utf-8")
    assert not (project_skills / "find-skills").exists()


# --- install-1 unit-2 (REQ-008 fail-closed / D4/D8) --------------------------


def test_user_without_user_id_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN non-admin has no user_id THEN install fails; backend/skills unchanged."""
    project_skills = _patch_dirs(tmp_path, monkeypatch)
    sentinel = project_skills / "keep-me"
    sentinel.mkdir()
    (sentinel / "SKILL.md").write_text("project", encoding="utf-8")

    out = _install(role="user", user_key=None, skill="find-skills")

    assert "fail-closed" in out.lower() or "sem user_id" in out.lower()
    assert "[OK]" not in out
    assert not (project_skills / "find-skills").exists()
    assert (sentinel / "SKILL.md").read_text(encoding="utf-8") == "project"
    # Telegram key without stamped user_id also fail-closed for sync resolver.
    out_tg = _install(role="user", user_key="telegram:12345", skill="find-skills")
    assert "[OK]" not in out_tg
    assert not (project_skills / "find-skills").exists()


# --- install-1 unit-3 (REQ-008 admin → project) ------------------------------


def test_admin_install_defaults_to_project_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN admin installs without for_user_id THEN backend/skills/<skill>/."""
    project_skills = _patch_dirs(tmp_path, monkeypatch)

    out = _install(role="admin", user_key="web:admin-1", skill="find-skills")

    assert "[OK]" in out
    installed = project_skills / "find-skills" / "SKILL.md"
    assert installed.is_file()
    assert not (user_skills_root("admin-1") / "find-skills" / "SKILL.md").exists()


# --- install-1 unit-4 (REQ-008 admin for_user_id) ----------------------------


def test_admin_install_for_user_id_lands_in_owned_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN admin installs with for_user_id=A THEN files/A/skills/<skill>/."""
    project_skills = _patch_dirs(tmp_path, monkeypatch)

    out = _install(
        role="admin",
        user_key="web:admin-1",
        skill="find-skills",
        for_user_id="user-a",
    )

    assert "[OK]" in out
    owned = user_skills_root("user-a") / "find-skills" / "SKILL.md"
    assert owned.is_file()
    assert not (project_skills / "find-skills").exists()


# --- install-1 unit-5 (REQ-007 allowlist) ------------------------------------


def test_allowlist_refuses_unknown_repo_for_any_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN repo not on allowlist THEN refused with permitted list (any role)."""
    project_skills = _patch_dirs(tmp_path, monkeypatch)
    monkeypatch.delenv("SKILLS_ALLOWLIST", raising=False)

    for role, user_key, for_user_id in (
        ("user", "web:user-a", None),
        ("admin", "web:admin-1", None),
        ("admin", "web:admin-1", "user-a"),
    ):
        out = _install(
            role=role,
            user_key=user_key,
            skill="evil-skill",
            for_user_id=for_user_id,
            repo="evil-org/malicious-skills",
        )
        assert "não permitido" in out.lower() or "not permitted" in out.lower()
        assert "vercel-labs/skills" in out
        assert "[OK]" not in out
        assert not (project_skills / "evil-skill").exists()
        assert not (user_skills_root("user-a") / "evil-skill").exists()


# --- install-1 unit-6 (user-owned-skills REQ-004) ----------------------------


def test_user_overlay_does_not_mutate_project_skill_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN user writes files/A/skills/pdf THEN backend/skills/pdf unchanged."""
    from src.agents.unified import agent as agent_mod
    from src.infrastructure.ownership.paths import user_files_root

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

    project_pdf = dirs["SKILLS_DIR"] / "pdf" / "SKILL.md"
    project_pdf.parent.mkdir(parents=True)
    original = "---\nname: pdf\ndescription: project pdf\n---\nproject body\n"
    project_pdf.write_text(original, encoding="utf-8")

    cfg = _cfg(role="user", user_key="web:user-a")
    with patch(
        "src.composition.backends.get_config",
        return_value=cfg,
    ):
        backend = agent_mod._build_backend_factory()(MagicMock())
    routes = backend.routes
    user_skills = routes["/user-skills/"]
    result = user_skills.write(
        "pdf/SKILL.md",
        "---\nname: pdf\ndescription: user overlay\n---\nuser body\n",
    )
    assert result.error is None

    assert project_pdf.read_text(encoding="utf-8") == original
    owned = user_skills_root("user-a") / "pdf" / "SKILL.md"
    assert owned.is_file()
    assert "user overlay" in owned.read_text(encoding="utf-8")
    assert user_files_root("user-a").exists()


# --- install-1 unit-8 (REQ-007 official agent-skills → user owned) -----------


def test_user_install_official_agent_skills_repo_lands_in_owned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN role=user installs from vercel-labs/agent-skills THEN owned tree."""
    project_skills = _patch_dirs(tmp_path, monkeypatch)
    monkeypatch.delenv("SKILLS_ALLOWLIST", raising=False)

    out = _install(
        role="user",
        user_key="web:user-a",
        repo="vercel-labs/agent-skills",
        skill="web-design-guidelines",
    )

    assert "[OK]" in out or "instalada" in out.lower()
    owned = user_skills_root("user-a") / "web-design-guidelines" / "SKILL.md"
    assert owned.is_file(), f"expected owned skill; got out={out!r}"
    assert not (project_skills / "web-design-guidelines").exists()


# --- install-1 unit-7 (REQ-008 local create) ---------------------------------


def test_user_local_create_lands_in_owned_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN user creates note-taker under owned path THEN not under backend/skills/."""
    from src.agents.unified import agent as agent_mod

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

    cfg = _cfg(role="user", user_key="web:user-a")
    with patch(
        "src.composition.backends.get_config",
        return_value=cfg,
    ):
        backend = agent_mod._build_backend_factory()(MagicMock())
    routes = backend.routes
    result = routes["/user-skills/"].write(
        "note-taker/SKILL.md",
        "---\nname: note-taker\ndescription: notes\n---\nbody\n",
    )
    assert result.error is None
    owned = user_skills_root("user-a") / "note-taker" / "SKILL.md"
    assert owned.is_file()
    assert not (dirs["SKILLS_DIR"] / "note-taker" / "SKILL.md").exists()
