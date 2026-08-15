"""session-file-sandbox task-backend-1: role-aware CompositeBackend routes."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.agents.unified import agent as agent_mod
from src.composition.backends import MEMORIES_PREFIX
from src.infrastructure.ownership.paths import user_files_root


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
    # Seed a fake source file under "repo" for ls assertions.
    (dirs["REPO_ROOT"] / "CLAUDE.md").write_text("# fake", encoding="utf-8")
    (dirs["SKILLS_DIR"] / "demo").mkdir(exist_ok=True)
    (dirs["SKILLS_DIR"] / "demo" / "SKILL.md").write_text("skill", encoding="utf-8")
    return dirs


def _routes_for(
    *,
    role: str,
    thread_id: str = "thread-1",
    user_key: str | None = "web:user-a",
) -> dict:
    configurable: dict = {"thread_id": thread_id, "role": role}
    if user_key is not None:
        configurable["user_key"] = user_key
    with patch(
        "src.composition.backends.get_config",
        return_value={"configurable": configurable},
    ):
        backend = agent_mod._build_backend_factory()(MagicMock())
    return backend.routes


def _fs_root_dirs(routes: dict) -> list[Path]:
    roots: list[Path] = []
    for be in routes.values():
        # deepagents FilesystemBackend stores the root as `cwd`.
        root = getattr(be, "cwd", None) or getattr(be, "root_dir", None)
        if root is not None:
            roots.append(Path(root).resolve())
    return roots


# --- unit-1 (REQ-001): no REPO_ROOT for role=user -----------------------------


def test_user_backend_does_not_mount_repo_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN role=user THEN no route has base_dir=REPO_ROOT; ls does not list source."""
    dirs = _patch_dirs(tmp_path, monkeypatch)
    routes = _routes_for(role="user", user_key="web:user-a")
    roots = _fs_root_dirs(routes)
    repo = dirs["REPO_ROOT"].resolve()
    assert repo not in roots, f"REPO_ROOT still mounted: {roots}"
    assert str(repo) not in routes


# --- unit-2 (REQ-005 / D11 / D14): files root, no OUTPUTS, skills RO ----------


def test_user_backend_files_skills_and_no_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN role=user THEN files=FILES_DIR/<uid>, no OUTPUTS_DIR, skills write denied."""
    from src.composition.backends import ReadOnlyFilesystemBackend

    dirs = _patch_dirs(tmp_path, monkeypatch)
    routes = _routes_for(role="user", user_key="web:user-a")
    roots = _fs_root_dirs(routes)

    expected_files = user_files_root("user-a").resolve()
    assert expected_files in roots
    assert (tmp_path / "files").resolve() not in roots  # not FILES_DIR root
    assert dirs["OUTPUTS_DIR"].resolve() not in roots
    assert str(dirs["OUTPUTS_DIR"].resolve()) not in routes
    assert MEMORIES_PREFIX in routes

    skills = routes.get("/skills/")
    assert isinstance(skills, ReadOnlyFilesystemBackend)
    result = skills.write("demo/SKILL.md", "hacked")
    assert result.error is not None
    assert (dirs["SKILLS_DIR"] / "demo" / "SKILL.md").read_text(encoding="utf-8") == "skill"


# --- unit-3 (REQ-006): admin keeps REPO_ROOT ---------------------------------


def test_admin_backend_keeps_repo_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN role=admin THEN REPO_ROOT remains mounted and listing source works."""
    dirs = _patch_dirs(tmp_path, monkeypatch)
    routes = _routes_for(role="admin", user_key="web:admin-1")
    roots = _fs_root_dirs(routes)
    repo = dirs["REPO_ROOT"].resolve()
    assert repo in roots
    assert str(repo) in routes

    backend = routes[str(repo)]
    content = backend.read("CLAUDE.md")
    # ReadResult has `.content` (raw) or stringifies with line numbers.
    raw = getattr(content, "content", None) or str(content)
    assert "fake" in raw


# --- unit-4 (REQ-002): user has no SPECIFY_DIR / TEMPLATES_DIR ---------------


def test_user_backend_does_not_mount_specify_or_templates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN role=user THEN SPECIFY_DIR and TEMPLATES_DIR are not mounted."""
    dirs = _patch_dirs(tmp_path, monkeypatch)
    (dirs["TEMPLATES_DIR"] / "template.md").write_text("sdd", encoding="utf-8")
    (dirs["SPECIFY_DIR"] / "specs").mkdir(parents=True, exist_ok=True)
    routes = _routes_for(role="user", user_key="web:user-a")
    roots = _fs_root_dirs(routes)
    specify = dirs["SPECIFY_DIR"].resolve()
    templates = dirs["TEMPLATES_DIR"].resolve()
    assert specify not in roots
    assert templates not in roots
    assert str(specify) not in routes
    assert str(templates) not in routes


# --- unit-5 (REQ-004): workspace of current thread --------------------------


def test_user_backend_workspace_is_owned_per_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN role=user THEN workspace route is WORKSPACE_DIR/<thread_id>."""
    dirs = _patch_dirs(tmp_path, monkeypatch)
    thread_id = "thread-1"
    routes = _routes_for(role="user", thread_id=thread_id, user_key="web:user-a")
    ws_prefix = str(dirs["WORKSPACE_DIR"])
    assert ws_prefix in routes
    backend = routes[ws_prefix]
    result = backend.write("scratch.txt", "hello-ws")
    assert result.error is None
    owned = dirs["WORKSPACE_DIR"] / thread_id / "scratch.txt"
    assert owned.is_file()
    assert owned.read_text(encoding="utf-8") == "hello-ws"
    # Other thread dir must not receive the write.
    other = dirs["WORKSPACE_DIR"] / "thread-other" / "scratch.txt"
    assert not other.exists()


# --- unit-6 (REQ-004): traversal / other-thread workspace deny --------------


def test_user_workspace_blocks_traversal_to_other_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN role=user path uses .. or other thread_id THEN op is refused."""
    dirs = _patch_dirs(tmp_path, monkeypatch)
    other = dirs["WORKSPACE_DIR"] / "thread-other"
    other.mkdir(parents=True, exist_ok=True)
    secret = other / "secret.txt"
    secret.write_text("leak-me", encoding="utf-8")

    routes = _routes_for(role="user", thread_id="thread-1", user_key="web:user-a")
    backend = routes[str(dirs["WORKSPACE_DIR"])]

    with pytest.raises(ValueError, match="[Tt]raversal"):
        backend.read("../thread-other/secret.txt")
    with pytest.raises(ValueError, match="[Tt]raversal"):
        backend.write("../thread-other/hacked.txt", "nope")

    assert secret.read_text(encoding="utf-8") == "leak-me"
    assert not (other / "hacked.txt").exists()


# --- soft gap (REQ-005): no identity ⇒ files not mounted --------------------


def test_user_backend_without_identity_does_not_mount_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN role=user and no resolvable user_id THEN files/ is not mounted."""
    _patch_dirs(tmp_path, monkeypatch)
    files_root = (tmp_path / "files").resolve()

    # No user_key at all.
    routes_none = _routes_for(role="user", user_key=None)
    roots_none = _fs_root_dirs(routes_none)
    assert files_root not in roots_none
    assert not any(str(files_root) in str(r) for r in roots_none)

    # Telegram-style key without explicit user_id → fail-closed (no files/).
    routes_tg = _routes_for(role="user", user_key="telegram:12345")
    roots_tg = _fs_root_dirs(routes_tg)
    assert files_root not in roots_tg
    assert user_files_root("12345").resolve() not in roots_tg
