"""Testes do StoreStyleRepository (infrastructure-adapters REQ-001).

Usam um Store falso (async) — sem Postgres. Verificam o roundtrip de ImageDesign
e a tolerância a itens legados no mesmo namespace.
"""
from src.domain.imaging import DesignStyle, ImageDesign
from src.infrastructure.persistence.store_style_repository import StoreStyleRepository


class _Item:
    def __init__(self, key, value):
        self.key = key
        self.value = value


class FakeStore:
    def __init__(self):
        self.data = {}

    async def aput(self, ns, key, value):
        self.data.setdefault(ns, {})[key] = value

    async def asearch(self, ns, limit=100):
        return [_Item(k, v) for k, v in self.data.get(ns, {}).items()]


async def test_latest_none_when_empty():
    assert await StoreStyleRepository(FakeStore()).latest("t1") is None


async def test_save_then_latest_roundtrip():
    repo = StoreStyleRepository(FakeStore())
    design = ImageDesign(
        prompt="banner IA",
        style=DesignStyle(color_palette="azul"),
        negative_prompt="sem logo",
    )
    await repo.save("t1", design)
    got = await repo.latest("t1")
    assert got.prompt == "banner IA"
    assert got.style.color_palette == "azul"
    assert got.negative_prompt == "sem logo"


async def test_latest_ignores_legacy_items_without_design_key():
    store = FakeStore()
    repo = StoreStyleRepository(store)
    await repo.save("t1", ImageDesign(prompt="estruturado", style=DesignStyle(art_style="realista")))
    # item legado gravado pela ferramenta antiga (design_plan livre, sem chave "design")
    store.data[("styles", "t1")]["legacy"] = {"design_plan": "texto livre", "created_at": "9999"}
    got = await repo.latest("t1")
    assert got.prompt == "estruturado"


async def test_save_persists_image_path_and_latest_image_path_returns_it():
    """REQ-005: o caminho da imagem gerada é persistido e recuperável."""
    repo = StoreStyleRepository(FakeStore())
    await repo.save("t1", ImageDesign(prompt="x"), image_path="/out/images/a.png")
    assert await repo.latest_image_path("t1") == "/out/images/a.png"


async def test_latest_image_path_none_for_legacy_records_without_path():
    """REQ-005: registros sem image_path (legado) fazem fallback para None."""
    repo = StoreStyleRepository(FakeStore())
    await repo.save("t1", ImageDesign(prompt="sem imagem"))  # sem image_path
    assert await repo.latest_image_path("t1") is None


async def test_latest_image_path_returns_most_recent():
    """REQ-005: retorna o caminho do registro mais recente com imagem."""
    repo = StoreStyleRepository(FakeStore())
    await repo.save("t1", ImageDesign(prompt="antigo"), image_path="/out/old.png")
    await repo.save("t1", ImageDesign(prompt="novo"), image_path="/out/new.png")
    assert await repo.latest_image_path("t1") == "/out/new.png"
