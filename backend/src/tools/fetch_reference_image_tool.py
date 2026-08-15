"""Tool `fetch_reference_image` — ferramenta COMPARTILHADA de fetch de imagem por URL.

Adapter fino da borda deepagents sobre o port `ReferenceImageFetchPort`: baixa e
valida uma imagem remota (só http/https, defesa SSRF, limite de tamanho/timeout,
formato por magic bytes) e devolve o caminho local. Disponível a TODOS os agentes;
o path retornado pode ser usado como referência na geração de imagem.
"""
from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from src.application.ports.reference_image_fetch import ReferenceImageFetchError
from src.composition.dependencies import build_reference_image_fetch
from src.infrastructure.media.image_signatures import sniff_image_mime
from src.infrastructure.ownership.session_writers import (
    MissingUserIdentityError,
    require_user_kind_dir,
)
from src.infrastructure.ownership.store import record_ownership


@tool
async def fetch_reference_image(url: str) -> dict:
    """Download an image from a public http/https URL to use as a reference.

    Validates scheme, blocks private/loopback hosts (SSRF), enforces a max size and
    timeout, and checks the image format. On success returns the local file path;
    that path can be passed as a reference to image generation.

    Returns a dict:
    - {"path": "/.../files/<user_id>/attachment/....png"} on success.
    - {"error": "<reason>"} when the URL is invalid, unsafe, too large, or not an image.
    """
    try:
        output_dir = await require_user_kind_dir("reference")
    except MissingUserIdentityError as exc:
        return {"error": str(exc)}

    try:
        path = await build_reference_image_fetch(output_dir=output_dir).fetch(url)
    except ReferenceImageFetchError as exc:
        return {"error": str(exc)}

    try:
        await record_ownership(kind="reference", filename=Path(path).name)
    except Exception as exc:  # noqa: BLE001 — fail-closed
        return {"error": f"Falha ao registrar ownership: {exc}"}

    return {"path": path}


@tool
def check_reference_image(path: str) -> dict:
    """Validate a LOCAL reference image path (e.g. an image the user uploaded).

    Use this to confirm an already-uploaded reference image before generating.
    This is the ONLY correct way to "look at" an uploaded reference path — do NOT
    use read_file/ls/glob on it (those operate on your workspace sandbox, not on
    the server's user attachment directory, and will fail).

    Args:
        path: absolute server path of the uploaded image (e.g. the path given in
            the user's message, under files/<user_id>/attachment/).

    Returns a dict:
    - {"ok": true, "path": "<path>", "mime": "image/jpeg",
       "note": "Reference is valid. Pass this exact path in `references` when calling
                create_image_from_prompt. Do not read the file yourself."}
    - {"ok": false, "error": "<reason>"} if the file is missing or not a supported image.
    """
    file = Path(path)
    try:
        data = file.read_bytes()
    except OSError as exc:
        return {"ok": False, "error": f"Referência inacessível: {path!r} ({exc})."}

    mime = sniff_image_mime(data)
    if mime is None:
        return {"ok": False, "error": f"Arquivo não é uma imagem suportada: {path!r}."}

    return {
        "ok": True,
        "path": str(file),
        "mime": mime,
        "note": (
            "Referência válida. Passe EXATAMENTE este path em `references` ao chamar "
            "create_image_from_prompt. NÃO leia o arquivo você mesmo."
        ),
    }
