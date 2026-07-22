"""Extração de conteúdo de anexos de chat para contexto do agente.

Após um upload bem-sucedido (`src/infrastructure/attachments/store.py`),
extrai o texto de anexos docx/xlsx/pdf/csv/txt via `markitdown` — a mesma
biblioteca já usada pela tool `read_document` (`read_document_tool.py`) —
e devolve um bloco pronto para ser anexado à `HumanMessage`, com o texto
limitado a um tamanho máximo de caracteres para não estourar o contexto
do modelo (attachment-content-extraction REQ-001/REQ-004). Anexos de
imagem usam `caption_image` (Gemini) em vez de extração de texto — decisão
de design "caption-as-text para v1", não blocos multimodais nativos
(REQ-003).
"""
from __future__ import annotations

import os
from pathlib import Path

from google import genai
from google.genai import types
from markitdown import MarkItDown

from src.infrastructure.attachments.store import StoredAttachment

_MAX_EXTRACTED_CHARS = 5_000
_CAPTION_MODEL = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")
_CAPTION_PROMPT = (
    "Describe this image in detail so it can be used as context in a text "
    "conversation."
)
_VISION_UNAVAILABLE_NOTE = "[Attachment: image — vision unavailable]"


def extract_and_inject(
    attachment: StoredAttachment, *, max_chars: int = _MAX_EXTRACTED_CHARS
) -> str:
    r"""Extrai o texto de `attachment` e devolve `"[Attachment: <filename>]\n<texto>"`.

    Trunca o texto extraído em `max_chars`, anexando um aviso quando isso
    acontece. Falhas de extração (arquivo corrompido, criptografado, ou sem
    texto extraível) NÃO propagam — devolvem
    `"[Attachment: <filename> — could not be read: <reason>]"` para que o
    resto da mensagem ainda seja processado. Anexos `image/*` são legendados
    via `caption_image` em vez de extraídos como texto.
    """
    try:
        if attachment.content_type.startswith("image/"):
            caption = caption_image(
                Path(attachment.storage_path).read_bytes(),
                content_type=attachment.content_type,
            )
            if caption == _VISION_UNAVAILABLE_NOTE:
                return _failure_block(attachment.filename, "vision unavailable")
            text = caption
        else:
            text = _extract_text(Path(attachment.storage_path))
    except Exception as exc:
        return _failure_block(attachment.filename, str(exc))

    if not text.strip():
        return _failure_block(attachment.filename, "no extractable text found")

    truncated = len(text) > max_chars
    body = text[:max_chars]
    if truncated:
        body += f"\n\n[...conteúdo truncado em {max_chars} caracteres.]"

    return f"[Attachment: {attachment.filename}]\n{body}"


def caption_image(image_bytes: bytes, *, content_type: str) -> str:
    """Gera uma legenda textual de `image_bytes` via Gemini.

    Se `GOOGLE_API_KEY` não estiver configurada, devolve
    `_VISION_UNAVAILABLE_NOTE` em vez de falhar — mantém a mensagem
    processável mesmo sem visão computacional disponível.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return _VISION_UNAVAILABLE_NOTE

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=_CAPTION_MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=content_type),
            _CAPTION_PROMPT,
        ],
    )
    return response.text or ""


def _failure_block(filename: str, reason: str) -> str:
    return f"[Attachment: {filename} — could not be read: {reason}]"


def _extract_text(path: Path) -> str:
    md = MarkItDown()
    result = md.convert(str(path))
    return result.text_content or ""
