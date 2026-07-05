"""Testes da tool create_image_from_prompt (REQ-004 / create-image-from-prompt).

O cliente Gemini é mockado — nenhum teste faz chamada real à API nem requer
GOOGLE_API_KEY. Cobrem retrocompatibilidade (prompt: str) e entrada estruturada
(ImageDesignInput), além do sidecar JSON de metadados.
"""
import json
from unittest.mock import MagicMock

import pytest

import src.tools.generate_image_tool as gt
from src.models.image_design import ImageDesignInput


def _fake_client(saved_paths: list):
    """Cliente Gemini falso: generate_content devolve 1 part com imagem."""
    part = MagicMock()
    part.inline_data = object()  # != None -> entra no ramo de geração
    image = MagicMock()
    # image.save(path) grava um arquivo real para o teste verificar existência
    image.save.side_effect = lambda p: (saved_paths.append(str(p)),
                                         open(p, "wb").write(b"PNG"))
    part.as_image.return_value = image

    response = MagicMock()
    response.parts = [part]

    client = MagicMock()
    client.models.generate_content.return_value = response
    return client


@pytest.fixture
def patched_tool(monkeypatch, tmp_path):
    saved = []
    monkeypatch.setattr(gt, "client", _fake_client(saved))
    monkeypatch.setattr(gt, "SPECIFY_DIR", tmp_path)
    return tmp_path, saved


def test_retrocompat_prompt_string(patched_tool):
    """REQ-004: chamada com prompt: str (interface antiga) funciona."""
    tmp_path, _ = patched_tool
    result = gt.create_image_from_prompt.func("um gato astronauta no espaço")

    assert result["url"].startswith("/api/images/")
    assert result["url"].endswith(".png")
    assert result["metadata"]["prompt"] == "um gato astronauta no espaço"
    # campos opcionais ausentes viram None
    assert result["metadata"]["art_style"] is None
    # a imagem foi salva no diretório configurado
    assert (tmp_path / result["url"].split("/")[-1]).exists()


def test_structured_design_input(patched_tool):
    """REQ-004: chamada com ImageDesignInput registra metadados de design."""
    tmp_path, _ = patched_tool
    design = ImageDesignInput(
        prompt="banner de IA para e-commerce",
        art_style="minimalista",
        color_palette="tons de azul",
        composition="regra dos terços",
        dimensions="1200x628",
        negative_prompt="sem texto",
    )
    result = gt.create_image_from_prompt.func(design)

    meta = result["metadata"]
    assert meta["prompt"] == "banner de IA para e-commerce"
    assert meta["art_style"] == "minimalista"
    assert meta["color_palette"] == "tons de azul"
    assert meta["composition"] == "regra dos terços"
    assert meta["dimensions"] == "1200x628"
    assert meta["negative_prompt"] == "sem texto"


def test_sidecar_metadata_written(patched_tool):
    """REQ-004: um sidecar JSON com os metadados é gravado junto da imagem."""
    tmp_path, _ = patched_tool
    result = gt.create_image_from_prompt.func("uma paisagem")

    image_name = result["url"].split("/")[-1]
    sidecar = tmp_path / image_name.replace(".png", "_metadata.json")
    assert sidecar.exists()
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["prompt"] == "uma paisagem"


def test_only_prompt_sent_to_gemini(patched_tool):
    """A API Gemini recebe apenas o texto do prompt (modelo ignora params estruturados)."""
    tmp_path, _ = patched_tool
    design = ImageDesignInput(prompt="robô simpático", art_style="cartoon")
    gt.create_image_from_prompt.func(design)

    _, kwargs = gt.client.models.generate_content.call_args
    assert kwargs["contents"] == ["robô simpático"]
