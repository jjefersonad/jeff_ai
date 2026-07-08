"""Testes da tool create_image_from_prompt como adapter fino (application REQ-004).

A tool agora traduz a entrada para o domínio e delega ao caso de uso
PlanAndCreateImage. O cliente Gemini e o Store são mockados — nenhum teste faz
chamada real nem requer GOOGLE_API_KEY/Postgres.
"""
from unittest.mock import MagicMock

import src.composition.dependencies as dep
import src.infrastructure.llm.gemini_image_adapter as gmod
import src.tools.generate_image_tool as gt
from src.domain.imaging import ImageDesign
from src.models.image_design import ImageDesignInput


def test_to_image_design_from_string():
    d = gt._to_image_design("só um gato")
    assert isinstance(d, ImageDesign)
    assert d.prompt == "só um gato"
    assert d.style.is_empty()


def test_to_image_design_maps_structured_fields():
    di = ImageDesignInput(
        prompt="banner de IA para e-commerce",
        art_style="minimalista",
        color_palette="tons de azul",
        composition="regra dos terços",
        dimensions="1200x628",
        negative_prompt="sem texto",
    )
    d = gt._to_image_design(di)
    assert d.style.art_style == "minimalista"
    assert d.style.color_palette == "tons de azul"
    assert d.style.composition == "regra dos terços"
    assert d.style.dimensions == "1200x628"
    assert d.negative_prompt == "sem texto"


def test_to_image_design_drops_freeform_dimensions_and_blanks():
    """Contrato tolerante: campos vazios viram None e dimensões livres são descartadas."""
    di = ImageDesignInput(
        prompt="x", art_style="   ", color_palette="verde", dimensions="quadrado"
    )
    d = gt._to_image_design(di)
    assert d.style.art_style is None
    assert d.style.color_palette == "verde"
    assert d.style.dimensions is None


def test_to_image_design_without_references_is_empty():
    """REQ-001: sem references, o design não carrega referências (text-only)."""
    d = gt._to_image_design(ImageDesignInput(prompt="x"))
    assert d.references == ()


def test_to_image_design_maps_references_paths():
    """REQ-001: caminhos em references viram ImageReference; vazios são ignorados."""
    di = ImageDesignInput(prompt="x", references=["/tmp/a.png", "  ", "/tmp/b.png"])
    d = gt._to_image_design(di)
    assert [r.path for r in d.references] == ["/tmp/a.png", "/tmp/b.png"]


async def test_tool_delegates_and_returns_path_url_metadata(monkeypatch, tmp_path):
    part = MagicMock()
    part.inline_data = object()
    image = MagicMock()
    image.save.side_effect = lambda p: open(p, "wb").write(b"PNG")
    part.as_image.return_value = image
    response = MagicMock()
    response.parts = [part]
    client = MagicMock()
    client.models.generate_content.return_value = response

    monkeypatch.setattr(gmod.genai, "Client", lambda *a, **k: client)
    monkeypatch.setattr(gmod, "_DEFAULT_OUTPUT_DIR", tmp_path)
    # A injeção do adapter/Store agora vive em composition.dependencies.
    monkeypatch.setattr(dep, "get_store", lambda: MagicMock())

    result = await gt.create_image_from_prompt.coroutine("um gato astronauta")

    assert set(result) == {"path", "url", "metadata"}
    assert result["url"].startswith("/api/images/") and result["url"].endswith(".png")
    assert result["metadata"]["prompt"] == "um gato astronauta"
    assert result["metadata"]["art_style"] is None
    assert (tmp_path / result["url"].split("/")[-1]).exists()
