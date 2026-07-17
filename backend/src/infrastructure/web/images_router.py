"""Rotas HTTP de imagens geradas e imagens de referência (upload).

Portado 1:1 de `backend/image_server.py` para ser montado como `APIRouter`
pelo `http.app` do backend LangGraph (`src/infrastructure/web/webapp.py`).
"""

from datetime import datetime as dt
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from src.infrastructure.media.reference_store import (
    ReferenceUploadError,
    store_reference_bytes,
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


@router.get("/api/images")
async def list_images(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """List generated images with pagination"""
    if not IMAGES_DIR.exists():
        return {"images": [], "total": 0}

    png_files = [
        f for f in IMAGES_DIR.iterdir()
        if f.is_file() and f.suffix.lower() == ".png"
    ]
    png_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    total = len(png_files)
    paginated_files = png_files[offset:offset + limit]

    images = []
    for f in paginated_files:
        filename = f.name
        timestamp_str = filename.replace(".png", "")
        try:
            timestamp_dt = dt.strptime(timestamp_str, "%Y%m%d%H%M%S")
            timestamp_iso = timestamp_dt.isoformat()
        except ValueError:
            timestamp_iso = dt.fromtimestamp(f.stat().st_mtime).isoformat()

        images.append({
            "filename": filename,
            "url": f"/api/images/{filename}",
            "timestamp": timestamp_iso
        })

    return {
        "images": images,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/api/images/{filename}")
async def serve_image(filename: str):
    """Serve a generated image file"""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not filename.lower().endswith(".png"):
        raise HTTPException(status_code=400, detail="Only PNG files are supported")

    image_path = IMAGES_DIR / filename

    try:
        resolved_path = image_path.resolve()
        resolved_images_dir = IMAGES_DIR.resolve()
        if not str(resolved_path).startswith(str(resolved_images_dir)):
            raise HTTPException(status_code=400, detail="Invalid filename")
    except (OSError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(
        path=str(image_path),
        media_type="image/png",
        headers={"Cache-Control": "max-age=3600"}
    )


@router.post("/api/references")
async def upload_reference(file: UploadFile = File(...)):
    """Recebe uma imagem de referência (upload), valida e salva localmente.

    Retorna o caminho local (usado como referência na geração), a URL para exibir
    a imagem e o nome do arquivo. Recusa arquivos vazios, grandes demais ou que
    não sejam imagens em formato suportado.
    """
    data = await file.read()
    try:
        path = store_reference_bytes(data, output_dir=REFERENCES_DIR)
    except ReferenceUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    filename = Path(path).name
    return {"path": path, "url": f"/api/references/{filename}", "filename": filename}


@router.get("/api/references/{filename}")
async def serve_reference(filename: str):
    """Serve uma imagem de referência salva por upload."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    suffix = Path(filename).suffix.lower()
    media_type = _REFERENCE_MEDIA_TYPES.get(suffix)
    if media_type is None:
        raise HTTPException(status_code=400, detail="Unsupported reference type")

    reference_path = REFERENCES_DIR / filename
    try:
        resolved_path = reference_path.resolve()
        if not str(resolved_path).startswith(str(REFERENCES_DIR.resolve())):
            raise HTTPException(status_code=400, detail="Invalid filename")
    except (OSError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not reference_path.exists():
        raise HTTPException(status_code=404, detail="Reference not found")

    return FileResponse(
        path=str(reference_path),
        media_type=media_type,
        headers={"Cache-Control": "max-age=3600"},
    )
