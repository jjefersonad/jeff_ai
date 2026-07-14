"""Testes do reference_store (consistent-imagery-generation REQ-004).

Lógica pura de validação/gravação do upload — sem FastAPI, sem rede. O magic-byte
sniff decide o formato; nome de arquivo é sempre gerado.
"""
import base64
from pathlib import Path

import pytest

from src.infrastructure.media.reference_store import (
    ReferenceUploadError,
    store_reference_bytes,
)

_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


def test_store_valid_png_returns_path(tmp_path):
    """REQ-004: upload válido é persistido com nome gerado e extensão correta."""
    path = store_reference_bytes(_PNG_1X1, output_dir=tmp_path)
    saved = Path(path)
    assert saved.exists()
    assert saved.parent == tmp_path
    assert saved.suffix == ".png"
    assert saved.read_bytes() == _PNG_1X1


def test_store_rejects_non_image(tmp_path):
    """REQ-004: arquivo que não é imagem suportada é recusado."""
    with pytest.raises(ReferenceUploadError, match="formato suportado"):
        store_reference_bytes(b"isto nao e uma imagem", output_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_store_rejects_oversized(tmp_path):
    """REQ-004: conteúdo acima do limite é recusado."""
    with pytest.raises(ReferenceUploadError, match="tamanho máximo"):
        store_reference_bytes(_PNG_1X1, output_dir=tmp_path, max_bytes=10)


def test_store_rejects_empty(tmp_path):
    with pytest.raises(ReferenceUploadError, match="vazio"):
        store_reference_bytes(b"", output_dir=tmp_path)


def test_store_generates_unique_names(tmp_path):
    """O nome é gerado (não confia no cliente) e não colide entre uploads."""
    p1 = store_reference_bytes(_PNG_1X1, output_dir=tmp_path)
    p2 = store_reference_bytes(_PNG_1X1, output_dir=tmp_path)
    assert p1 != p2
