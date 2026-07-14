"""Detecção de formato de imagem por magic bytes — sem depender de Pillow.

Compartilhado pelos adapters que precisam validar/rotular bytes de imagem
(geração Gemini e fetch de referência por URL).
"""
from __future__ import annotations

# (assinatura, mime) para formatos com prefixo fixo.
_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
)

_MIME_EXTENSION: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/webp": ".webp",
}


def sniff_image_mime(data: bytes) -> str | None:
    """Detecta o mime type de uma imagem pelas magic bytes; None se não suportado."""
    for signature, mime_type in _IMAGE_SIGNATURES:
        if data.startswith(signature):
            return mime_type
    # WEBP: "RIFF"...."WEBP" (o tamanho do arquivo fica entre os dois marcadores).
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def extension_for_mime(mime_type: str) -> str:
    """Extensão de arquivo para um mime type de imagem suportado (fallback .bin)."""
    return _MIME_EXTENSION.get(mime_type, ".bin")
