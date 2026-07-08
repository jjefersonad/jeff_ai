"""Testes do caso de uso PlanAndCreateImage (application-use-cases REQ-001).

Exercitam a regra completa com dublês (fakes) dos ports — sem Gemini, Postgres
nem filesystem.
"""
import pytest

from src.application.ports.image_gen import GeneratedImage, ImageGenPort
from src.application.ports.style_repository import StyleRepositoryPort
from src.application.use_cases import PlanAndCreateImage
from src.domain.imaging import DesignStyle, ImageDesign


class FakeImageGen(ImageGenPort):
    def __init__(self):
        self.calls = []

    async def generate(self, design):
        self.calls.append(design)
        return GeneratedImage(
            path="/tmp/x.png", url="/api/images/x.png", metadata=design.metadata()
        )


class FakeStyleRepo(StyleRepositoryPort):
    def __init__(self, latest=None, latest_image=None):
        self.saved = []
        self._latest = latest
        self._latest_image = latest_image

    async def save(self, thread_id, design, image_path=None):
        self.saved.append((thread_id, design, image_path))

    async def latest(self, thread_id):
        return self._latest

    async def latest_image_path(self, thread_id):
        return self._latest_image


def _design():
    return ImageDesign(
        prompt="gato astronauta",
        style=DesignStyle(art_style="realista", dimensions="1:1"),
    )


async def test_execute_generates_without_saving_style():
    gen, repo = FakeImageGen(), FakeStyleRepo()
    res = await PlanAndCreateImage(gen, repo).execute(_design())
    assert isinstance(res, GeneratedImage)
    assert res.url == "/api/images/x.png"
    assert res.metadata["art_style"] == "realista"
    assert len(gen.calls) == 1
    assert repo.saved == []


async def test_execute_remembers_style_and_image_path_when_flagged():
    """REQ-005: ao lembrar o estilo, o caminho da imagem gerada é persistido."""
    gen, repo = FakeImageGen(), FakeStyleRepo()
    design = _design()
    await PlanAndCreateImage(gen, repo).execute(
        design, thread_id="t1", remember_style=True
    )
    assert repo.saved == [("t1", design, "/tmp/x.png")]


async def test_execute_remember_without_thread_id_raises():
    uc = PlanAndCreateImage(FakeImageGen(), FakeStyleRepo())
    with pytest.raises(ValueError):
        await uc.execute(_design(), remember_style=True)


async def test_prepare_same_vibe_returns_none_when_empty():
    uc = PlanAndCreateImage(FakeImageGen(), FakeStyleRepo(latest=None))
    assert await uc.prepare_same_vibe("t1", "cachorro") is None


async def test_prepare_same_vibe_reuses_style_without_previous_image():
    """REQ-005 fallback: sem imagem anterior, reutiliza só o estilo (sem referência)."""
    prev = _design()
    uc = PlanAndCreateImage(FakeImageGen(), FakeStyleRepo(latest=prev, latest_image=None))
    nd = await uc.prepare_same_vibe("t1", "cachorro surfista")
    assert nd.prompt == "cachorro surfista"
    assert nd.style == prev.style
    assert nd.references == ()


async def test_prepare_same_vibe_includes_previous_image_as_reference():
    """REQ-005: com imagem anterior, ela entra como referência visual."""
    prev = _design()
    uc = PlanAndCreateImage(
        FakeImageGen(), FakeStyleRepo(latest=prev, latest_image="/out/prev.png")
    )
    nd = await uc.prepare_same_vibe("t1", "cachorro surfista")
    assert nd.style == prev.style
    assert [r.path for r in nd.references] == ["/out/prev.png"]
