"""
Servidor minimalista para servir imagens geradas.
Roda em uma porta separada do LangGraph API.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path
from datetime import datetime as dt

app = FastAPI(title="Jeff AI Image Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

IMAGES_DIR = Path("/deps/backend/outputs/images")


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/api/images")
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


@app.get("/api/images/{filename}")
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
