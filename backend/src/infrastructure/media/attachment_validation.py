"""Validação de anexos de chat (upload) por magic bytes — texto, PDF, OOXML e imagem.

Lógica pura (stdlib apenas), espelhando `reference_store.py`/`image_signatures.py`:
sniffa os bytes reais do arquivo (não a extensão/MIME declarado pelo cliente) e
valida o tamanho, antes de qualquer persistência. CSV/TXT não têm assinatura de
bytes própria — são reconhecidos por decodificarem como texto válido (sem NUL
bytes), e o `content_type` final vem da extensão declarada apenas depois dessa
confirmação, nunca antes.
"""
from __future__ import annotations

import zipfile
from io import BytesIO

from src.infrastructure.media.image_signatures import sniff_image_mime

_PDF_SIGNATURE = b"%PDF-"
_OOXML_SIGNATURE = b"PK\x03\x04"

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_TEXT_EXTENSION_MIME: dict[str, str] = {
    ".csv": "text/csv",
    ".txt": "text/plain",
}


class AttachmentValidationError(Exception):
    """Upload de anexo inválido (vazio, grande demais, ou tipo não suportado)."""


def enforce_size_limit(size_bytes: int, max_bytes: int) -> None:
    """Levanta AttachmentValidationError se `size_bytes` exceder `max_bytes`."""
    if size_bytes > max_bytes:
        raise AttachmentValidationError(
            f"Anexo excede o tamanho máximo de {max_bytes} bytes."
        )


def sniff_and_validate(data: bytes, *, declared_filename: str) -> str:
    """Detecta o content_type real dos bytes; levanta AttachmentValidationError se não suportado.

    Ordem de sniff: imagem (magic bytes) → PDF (prefixo `%PDF-`) → OOXML
    docx/xlsx (ZIP com a entrada interna característica) → texto (decodifica
    como UTF-8 sem NUL bytes, content_type resolvido pela extensão declarada).
    """
    if not data:
        raise AttachmentValidationError("Anexo vazio.")

    image_mime = sniff_image_mime(data)
    if image_mime is not None:
        return image_mime

    if data.startswith(_PDF_SIGNATURE):
        return "application/pdf"

    if data.startswith(_OOXML_SIGNATURE):
        ooxml_mime = _sniff_ooxml_mime(data)
        if ooxml_mime is not None:
            return ooxml_mime
        raise AttachmentValidationError("Arquivo enviado não é um formato suportado.")

    if _looks_like_text(data):
        text_mime = _TEXT_EXTENSION_MIME.get(_extension(declared_filename))
        if text_mime is not None:
            return text_mime

    raise AttachmentValidationError("Arquivo enviado não é um formato suportado.")


def _sniff_ooxml_mime(data: bytes) -> str | None:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile:
        return None
    if "word/document.xml" in names:
        return _DOCX_MIME
    if "xl/workbook.xml" in names:
        return _XLSX_MIME
    return None


def _looks_like_text(data: bytes) -> bool:
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _extension(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot != -1 else ""
