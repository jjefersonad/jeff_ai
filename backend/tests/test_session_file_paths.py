"""session-file-sandbox foundation: FILES_DIR helpers + authorize_session_path."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.ownership import paths as file_paths
from src.infrastructure.ownership.path_guard import (
    PathNotAuthorizedError,
    authorize_session_path,
)


def test_kind_to_subdir_maps_docs_images_attachment() -> None:
    assert file_paths.kind_to_subdir("docx") == "docs"
    assert file_paths.kind_to_subdir("xlsx") == "docs"
    assert file_paths.kind_to_subdir("pptx") == "docs"
    assert file_paths.kind_to_subdir("pdf") == "docs"
    assert file_paths.kind_to_subdir("html") == "docs"
    assert file_paths.kind_to_subdir("image") == "images"
    assert file_paths.kind_to_subdir("reference") == "attachment"


def test_user_files_root_and_kind_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FILES_DIR", str(tmp_path))
    root = file_paths.user_files_root("user-a")
    assert root == tmp_path / "user-a"
    assert file_paths.user_kind_dir("user-a", "docx") == tmp_path / "user-a" / "docs"
    assert file_paths.user_kind_dir("user-a", "image") == tmp_path / "user-a" / "images"
    assert file_paths.user_kind_dir("user-a", "reference") == (
        tmp_path / "user-a" / "attachment"
    )


def test_user_skills_root_equals_files_dir_user_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """user-project-skills-layers-task-paths-1-unit-1 (user-owned-skills REQ-001)."""
    monkeypatch.setenv("FILES_DIR", str(tmp_path))
    assert file_paths.user_skills_root("A") == tmp_path / "A" / "skills"
    assert file_paths.user_skills_root("A") == file_paths.user_files_root("A") / "skills"


def test_user_skills_root_not_under_project_skills_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """user-project-skills-layers-task-paths-1-unit-2 (user-owned-skills REQ-001/005)."""
    files = tmp_path / "files"
    workspace = tmp_path / "workspace"
    project_skills = tmp_path / "backend" / "skills"
    files.mkdir()
    workspace.mkdir()
    project_skills.mkdir(parents=True)
    monkeypatch.setenv("FILES_DIR", str(files))
    monkeypatch.setenv("WORKSPACE_DIR", str(workspace))

    root = file_paths.user_skills_root("user-a")
    assert root == files / "user-a" / "skills"
    assert root.is_relative_to(files)
    assert not root.is_relative_to(project_skills)
    # Durable under owned files, not per-thread workspace (REQ-005).
    assert not root.is_relative_to(workspace)


@pytest.mark.asyncio
async def test_authorize_denies_other_users_files_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FILES_DIR", str(tmp_path / "files"))
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "workspace"))
    other = tmp_path / "files" / "user-b" / "images" / "foo.png"
    other.parent.mkdir(parents=True)
    other.write_bytes(b"x")

    with pytest.raises(PathNotAuthorizedError):
        await authorize_session_path(
            other,
            user_id="user-a",
            role="user",
            thread_id="thread-1",
        )


@pytest.mark.asyncio
async def test_authorize_allows_workspace_without_generated_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FILES_DIR", str(tmp_path / "files"))
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("WORKSPACE_DIR", str(workspace))
    scratch = workspace / "thread-1" / "scratch.txt"
    scratch.parent.mkdir(parents=True)
    scratch.write_text("ok", encoding="utf-8")

    await authorize_session_path(
        scratch,
        user_id="user-a",
        role="user",
        thread_id="thread-1",
    )
