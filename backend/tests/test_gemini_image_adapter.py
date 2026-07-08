"""Testes do GeminiImageAdapter (infrastructure-adapters REQ-001/REQ-003).

O cliente Gemini é mockado — nenhum teste faz chamada real nem requer
GOOGLE_API_KEY. Verificam a conversão da resposta crua em GeneratedImage, o
sidecar de metadados e que só o prompt é enviado à API.
"""
import base64
import json
from unittest.mock import MagicMock

import pytest
from google.genai import types

import src.infrastructure.llm.gemini_image_adapter as gmod
from src.application.ports.image_gen import GeneratedImage
from src.domain.imaging import DesignStyle, ImageDesign, ImageReference

# PNG 1x1 válido (magic bytes reais) — evita depender de Pillow nos testes.
_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


def _write_png(path) -> str:
    """Grava um PNG mínimo real no disco e retorna o caminho (para referências)."""
    path.write_bytes(_PNG_1X1)
    return str(path)


def _fake_client_factory(saved):
    def make(*args, **kwargs):
        part = MagicMock()
        part.inline_data = object()  # != None -> ramo de geração
        image = MagicMock()
        image.save.side_effect = lambda p: (
            saved.append(str(p)),
            open(p, "wb").write(b"PNG"),
        )
        part.as_image.return_value = image
        response = MagicMock()
        response.parts = [part]
        client = MagicMock()
        client.models.generate_content.return_value = response
        return client

    return make


@pytest.fixture
def adapter(monkeypatch, tmp_path):
    saved = []
    monkeypatch.setattr(gmod.genai, "Client", _fake_client_factory(saved))
    return gmod.GeminiImageAdapter(output_dir=tmp_path), tmp_path


async def test_generate_returns_generated_image_and_saves(adapter):
    ad, tmp_path = adapter
    res = await ad.generate(
        ImageDesign(prompt="uma paisagem", style=DesignStyle(art_style="realista"))
    )
    assert isinstance(res, GeneratedImage)
    assert res.url.startswith("/api/images/") and res.url.endswith(".png")
    assert res.metadata["art_style"] == "realista"
    assert (tmp_path / res.url.split("/")[-1]).exists()


async def test_generate_writes_sidecar_metadata(adapter):
    ad, tmp_path = adapter
    res = await ad.generate(ImageDesign(prompt="uma paisagem"))
    name = res.url.split("/")[-1]
    sidecar = tmp_path / name.replace(".png", "_metadata.json")
    assert sidecar.exists()
    assert json.loads(sidecar.read_text(encoding="utf-8"))["prompt"] == "uma paisagem"


async def test_only_prompt_sent_to_gemini(adapter):
    """REQ-001: sem referências, só o prompt é enviado (comportamento text-only)."""
    ad, _ = adapter
    await ad.generate(
        ImageDesign(prompt="robô simpático", style=DesignStyle(art_style="cartoon"))
    )
    _, kwargs = ad._client.models.generate_content.call_args
    assert kwargs["contents"] == ["robô simpático"]


async def test_references_sent_before_prompt(adapter):
    """REQ-001/REQ-002: referências entram ANTES do prompt, como imagens PIL."""
    ad, tmp_path = adapter
    ref_a = _write_png(tmp_path / "ref_a.png")
    ref_b = _write_png(tmp_path / "ref_b.png")
    await ad.generate(
        ImageDesign(
            prompt="mesma vibe",
            references=[ImageReference(path=ref_a), ImageReference(path=ref_b)],
        )
    )
    _, kwargs = ad._client.models.generate_content.call_args
    contents = kwargs["contents"]
    assert len(contents) == 3
    assert contents[-1] == "mesma vibe"
    assert all(isinstance(c, types.Part) for c in contents[:2])


async def test_unreadable_reference_raises_before_api_call(adapter):
    """REQ-006: referência inexistente aborta antes de chamar a API; nada é gerado."""
    ad, tmp_path = adapter
    missing = str(tmp_path / "nao_existe.png")
    with pytest.raises(RuntimeError, match="ilegível ou inexistente"):
        await ad.generate(
            ImageDesign(prompt="x", references=[ImageReference(path=missing)])
        )
    ad._client.models.generate_content.assert_not_called()


async def test_unsupported_reference_format_raises(adapter):
    """REQ-006: arquivo que não é imagem suportada é recusado antes da API."""
    ad, tmp_path = adapter
    bad = tmp_path / "nao_imagem.txt"
    bad.write_bytes(b"isto nao e uma imagem")
    with pytest.raises(RuntimeError, match="formato não suportado"):
        await ad.generate(
            ImageDesign(prompt="x", references=[ImageReference(path=str(bad))])
        )
    ad._client.models.generate_content.assert_not_called()
