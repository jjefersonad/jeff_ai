"""Rotas HTTP de imagens geradas e imagens de referência (upload).

Portado 1:1 de `backend/image_server.py` para ser montado como `APIRouter`
pelo `http.app` do backend LangGraph (`src/infrastructure/web/webapp.py`).

Listagem e serve de PNGs geradas respeitam `generated_files`
(`media-ownership-authorization` / `fix-image-list-user-isolation`):
`role=user` só vê/baixa o que possui; `role=admin` vê o diretório completo;
órfãs (sem linha) são invisíveis a user.

session-file-sandbox (D7/D12/D13): path derivado `files/<owner>/images/`;
`list_images` não varre só `IMAGES_DIR` global; fallback legado admin-only.
"""

from datetime import datetime as dt
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.users import User
from src.infrastructure.media.reference_store import (
    ReferenceUploadError,
    store_reference_bytes,
)
from src.infrastructure.ownership.paths import (
    files_dir,
    resolve_owned_file_path,
    user_kind_dir,
)
from src.infrastructure.ownership.store import (
    get_file_owner,
    is_authorized,
    list_owned_filenames,
    record_ownership,
)

router = APIRouter()

IMAGES_DIR = Path("/deps/backend/outputs/images")
REFERENCES_DIR = Path("/deps/backend/outputs/references")

# Mime types servidos para imagens de referência (upload aceita vários formatos).
_REFERENCE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
}


def _safe_resolve(path: Path, base: Path) -> Path | None:
    try:
        resolved = path.resolve()
    except (OSError, ValueError):
        return None
    if not str(resolved).startswith(str(base.resolve())):
        return None
    return resolved


def _collect_pngs_under(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return [
        f
        for f in directory.iterdir()
        if f.is_file() and f.suffix.lower() == ".png"
    ]


def _list_image_files_for_user(user: User, owned: frozenset[str]) -> list[Path]:
    """User: only owned filenames that exist under files/<uid>/images/."""
    images_dir = user_kind_dir(user.id, "image")
    files: list[Path] = []
    for name in owned:
        candidate = images_dir / name
        resolved = _safe_resolve(candidate, images_dir)
        if (
            resolved is not None
            and resolved.is_file()
            and resolved.suffix.lower() == ".png"
        ):
            files.append(resolved)
    return files


def _list_image_files_for_admin() -> list[Path]:
    """Admin: files/*/images/*.png plus legacy IMAGES_DIR (unique by name)."""
    by_name: dict[str, Path] = {}
    root = files_dir()
    if root.is_dir():
        for user_dir in root.iterdir():
            if not user_dir.is_dir():
                continue
            for png in _collect_pngs_under(user_dir / "images"):
                by_name[png.name] = png
    for png in _collect_pngs_under(IMAGES_DIR):
        by_name.setdefault(png.name, png)
    return list(by_name.values())


def _resolve_image_path(
    *, filename: str, owner_id: str | None, role: str
) -> Path | None:
    if owner_id:
        try:
            derived = resolve_owned_file_path(
                user_id=owner_id, kind="image", filename=filename
            )
        except ValueError:
            derived = None
        if derived is not None:
            resolved = _safe_resolve(derived, derived.parent)
            if resolved is not None and resolved.is_file():
                return resolved

    if role == "admin":
        resolved = _safe_resolve(IMAGES_DIR / filename, IMAGES_DIR)
        if resolved is not None and resolved.is_file():
            return resolved

    return None


def _image_timestamp_iso(path: Path) -> str:
    timestamp_str = path.name.replace(".png", "")
    try:
        return dt.strptime(timestamp_str, "%Y%m%d%H%M%S").isoformat()
    except ValueError:
        return dt.fromtimestamp(path.stat().st_mtime).isoformat()


@router.get("/api/images")
async def list_images(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User | None = Depends(require_auth),
):
    """List generated images with pagination (scoped by ownership for role=user)."""
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if user.role == "admin":
        png_files = _list_image_files_for_admin()
    else:
        owned = await list_owned_filenames(kind="image", user_id=user.id)
        png_files = _list_image_files_for_user(user, owned)

    png_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    total = len(png_files)
    paginated_files = png_files[offset : offset + limit]

    images = [
        {
            "filename": f.name,
            "url": f"/api/images/{f.name}",
            "timestamp": _image_timestamp_iso(f),
        }
        for f in paginated_files
    ]

    return {
        "images": images,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/api/images/{filename}")
async def serve_image(
    filename: str,
    user: User | None = Depends(require_auth),
):
    """Serve a generated image file (ownership-gated for role=user)."""
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not filename.lower().endswith(".png"):
        raise HTTPException(status_code=400, detail="Only PNG files are supported")

    if not await is_authorized(kind="image", filename=filename, user=user):
        raise HTTPException(status_code=404, detail="Image not found")

    owner_id = await get_file_owner(kind="image", filename=filename)
    resolved = _resolve_image_path(
        filename=filename, owner_id=owner_id, role=user.role
    )
    if resolved is None:
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(
        path=str(resolved),
        media_type="image/png",
        headers={"Cache-Control": "max-age=3600"},
    )


@router.post("/api/references")
async def upload_reference(
    file: UploadFile = File(...),
    user: User | None = Depends(require_auth),
):
    """Recebe uma imagem de referência (upload), valida e salva localmente.

    Retorna o caminho local (usado como referência na geração), a URL para exibir
    a imagem e o nome do arquivo. Recusa arquivos vazios, grandes demais ou que
    não sejam imagens em formato suportado. Persiste em
    `files/<user_id>/attachment/` e registra ownership `kind=reference`.
    """
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    data = await file.read()
    try:
        path = store_reference_bytes(
            data,
            output_dir=user_kind_dir(user.id, "reference"),
        )
    except ReferenceUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    filename = Path(path).name
    await record_ownership(kind="reference", filename=filename, user_id=user.id)
    return {"path": path, "url": f"/api/references/{filename}", "filename": filename}


@router.get("/api/references/{filename}")
async def serve_reference(
    filename: str,
    user: User | None = Depends(require_auth),
):
    """Serve uma imagem de referência (auth + ownership; path derivado D13)."""
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    suffix = Path(filename).suffix.lower()
    media_type = _REFERENCE_MEDIA_TYPES.get(suffix)
    if media_type is None:
        raise HTTPException(status_code=400, detail="Unsupported reference type")

    if not await is_authorized(kind="reference", filename=filename, user=user):
        raise HTTPException(status_code=404, detail="Reference not found")

    owner_id = await get_file_owner(kind="reference", filename=filename)
    resolved: Path | None = None
    if owner_id:
        try:
            derived = resolve_owned_file_path(
                user_id=owner_id, kind="reference", filename=filename
            )
        except ValueError:
            derived = None
        if derived is not None:
            resolved = _safe_resolve(derived, derived.parent)
            if resolved is not None and not resolved.is_file():
                resolved = None

    if resolved is None and user.role == "admin":
        resolved = _safe_resolve(REFERENCES_DIR / filename, REFERENCES_DIR)
        if resolved is not None and not resolved.is_file():
            resolved = None

    if resolved is None:
        raise HTTPException(status_code=404, detail="Reference not found")

    return FileResponse(
        path=str(resolved),
        media_type=media_type,
        headers={"Cache-Control": "max-age=3600"},
    )
