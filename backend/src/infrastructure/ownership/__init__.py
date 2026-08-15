"""Rastreio de ownership por usuário para recursos gerados (documentos, imagens)."""

from src.infrastructure.ownership.path_guard import (
    PathNotAuthorizedError,
    authorize_session_path,
)
from src.infrastructure.ownership.paths import (
    files_dir,
    kind_to_subdir,
    resolve_owned_file_path,
    user_files_root,
    user_kind_dir,
    user_skills_root,
    workspace_dir,
)
from src.infrastructure.ownership.session_writers import (
    MissingUserIdentityError,
    require_user_docs_dir,
    require_user_id,
    require_user_kind_dir,
)

__all__ = [
    "MissingUserIdentityError",
    "PathNotAuthorizedError",
    "authorize_session_path",
    "files_dir",
    "kind_to_subdir",
    "require_user_docs_dir",
    "require_user_id",
    "require_user_kind_dir",
    "resolve_owned_file_path",
    "user_files_root",
    "user_kind_dir",
    "user_skills_root",
    "workspace_dir",
]
