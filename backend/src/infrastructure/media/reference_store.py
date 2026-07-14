"""Persistência de imagens de referência enviadas por upload.

Lógica pura (stdlib apenas) de validação + gravação, compartilhável pela rota
HTTP de upload. Valida tamanho e formato (magic bytes) e salva com nome gerado
em `outputs/references/`, retornando o caminho local.
"""
from __future__ import annotations

import datetime
import uuid
from pathlib import Path

from src.infrastructure.media.image_signatures import (
    extension_for_mime,
    sniff_image_mime,
)

_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


class ReferenceUploadError(Exception):
    """Upload de imagem de referência inválido (vazio, grande demais, ou não-imagem)."""


def store_reference_bytes(
    data: bytes,
    *,
    output_dir: Path,
    max_bytes: int = _DEFAULT_MAX_BYTES,
) -> str:
    """Valida e salva os bytes de uma imagem de referência; retorna o path local.

    Levanta `ReferenceUploadError` se o conteúdo for vazio, exceder `max_bytes`,
    ou não for uma imagem em formato suportado (detectado por magic bytes). O nome
    do arquivo é sempre gerado — o nome enviado pelo cliente nunca é usado.
    """
    if not data:
        raise ReferenceUploadError("Arquivo de imagem vazio.")
    if len(data) > max_bytes:
        raise ReferenceUploadError(
            f"Imagem excede o tamanho máximo de {max_bytes} bytes."
        )

    mime_type = sniff_image_mime(data)
    if mime_type is None:
        raise ReferenceUploadError("Arquivo enviado não é uma imagem em formato suportado.")

    output_dir.mkdir(parents=True, exist_ok=True)
    name = f"{_timestamp()}-{uuid.uuid4().hex[:8]}{extension_for_mime(mime_type)}"
    path = output_dir / name
    path.write_bytes(data)
    return str(path)


def _timestamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d%H%M%S")
