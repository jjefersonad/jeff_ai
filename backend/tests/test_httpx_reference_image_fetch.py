"""Testes do HttpxReferenceImageFetch (consistent-imagery-generation REQ-003).

A rede é mockada via httpx.MockTransport — nenhum teste faz chamada real. Hosts
usam IP público literal (93.184.216.34) para passar a checagem de SSRF sem DNS;
loopback/esquemas inválidos são recusados antes de qualquer download.
"""
import base64
from pathlib import Path

import httpx
import pytest

from src.application.ports.reference_image_fetch import ReferenceImageFetchError
from src.infrastructure.web.httpx_reference_image_fetch import HttpxReferenceImageFetch

_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)
_PUBLIC_URL = "http://93.184.216.34/img.png"


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


async def test_fetch_downloads_and_saves_valid_image(tmp_path):
    """REQ-003: URL de imagem válida é baixada, salva e o path é retornado."""
    transport = _transport(
        lambda req: httpx.Response(200, content=_PNG_1X1, headers={"content-type": "image/png"})
    )
    adapter = HttpxReferenceImageFetch(output_dir=tmp_path, transport=transport)
    path = await adapter.fetch(_PUBLIC_URL)
    saved = Path(path)
    assert saved.exists()
    assert saved.parent == tmp_path
    assert saved.suffix == ".png"
    assert saved.read_bytes() == _PNG_1X1


@pytest.mark.parametrize("bad_url", ["file:///etc/passwd", "ftp://example.com/x.png"])
async def test_fetch_rejects_disallowed_scheme(tmp_path, bad_url):
    """REQ-003: só http/https são aceitos."""
    adapter = HttpxReferenceImageFetch(output_dir=tmp_path)
    with pytest.raises(ReferenceImageFetchError, match="não permitido"):
        await adapter.fetch(bad_url)


@pytest.mark.parametrize("ssrf_url", ["http://127.0.0.1/x.png", "http://localhost/x.png"])
async def test_fetch_blocks_private_and_loopback_hosts(tmp_path, ssrf_url):
    """REQ-003: hosts privados/loopback são bloqueados (SSRF)."""
    adapter = HttpxReferenceImageFetch(output_dir=tmp_path)
    with pytest.raises(ReferenceImageFetchError, match="SSRF"):
        await adapter.fetch(ssrf_url)


async def test_fetch_rejects_oversized_image(tmp_path):
    """REQ-003: conteúdo acima do tamanho máximo é recusado."""
    transport = _transport(lambda req: httpx.Response(200, content=b"x" * 100))
    adapter = HttpxReferenceImageFetch(output_dir=tmp_path, max_bytes=10, transport=transport)
    with pytest.raises(ReferenceImageFetchError, match="tamanho máximo"):
        await adapter.fetch(_PUBLIC_URL)


async def test_fetch_rejects_non_image_content(tmp_path):
    """REQ-003: URL que não retorna imagem suportada é recusada."""
    transport = _transport(lambda req: httpx.Response(200, content=b"isto nao e imagem"))
    adapter = HttpxReferenceImageFetch(output_dir=tmp_path, transport=transport)
    with pytest.raises(ReferenceImageFetchError, match="formato suportado"):
        await adapter.fetch(_PUBLIC_URL)


async def test_fetch_wraps_network_errors(tmp_path):
    """REQ-003: erro de rede/timeout vira ReferenceImageFetchError claro."""
    def boom(req):
        raise httpx.ConnectTimeout("timed out")

    adapter = HttpxReferenceImageFetch(output_dir=tmp_path, transport=_transport(boom))
    with pytest.raises(ReferenceImageFetchError, match="Falha ao baixar"):
        await adapter.fetch(_PUBLIC_URL)
