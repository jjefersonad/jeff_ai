"""Testes do domínio de imaging (domain-model REQ-002/REQ-003/REQ-004).

Puro: sem framework, sem I/O — exercita invariantes de DesignStyle/ImageDesign
e o domain service de consistência de estilo.
"""
import pytest

from src.domain.imaging import (
    DesignStyle,
    ImageDesign,
    ImageReference,
    merge_style,
    same_vibe,
)
from src.domain.shared.errors import DomainError


def test_design_style_normalizes_and_accepts_valid():
    s = DesignStyle(art_style="  minimalista ", color_palette="azul", dimensions="16:9")
    assert s.art_style == "minimalista"
    assert s.dimensions == "16:9"
    assert not s.is_empty()


def test_empty_design_style_is_empty():
    assert DesignStyle().is_empty()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"art_style": "   "},
        {"color_palette": ""},
        {"dimensions": "banana"},
        {"dimensions": "1080"},
        {"art_style": 123},
    ],
)
def test_design_style_rejects_invalid(kwargs):
    """domain-model REQ-002: dados inválidos falham na construção (sem objeto parcial)."""
    with pytest.raises(DomainError):
        DesignStyle(**kwargs)


@pytest.mark.parametrize("dims", ["1080x1080", "1200x628", "16:9", "1:1"])
def test_design_style_accepts_valid_dimensions(dims):
    assert DesignStyle(dimensions=dims).dimensions == dims


@pytest.mark.parametrize("bad", ["", "   "])
def test_image_design_requires_prompt(bad):
    with pytest.raises(DomainError):
        ImageDesign(prompt=bad)


def test_image_design_metadata_shape():
    d = ImageDesign(
        prompt=" gato ",
        style=DesignStyle(art_style="realista"),
        negative_prompt=" sem texto ",
    )
    assert d.metadata() == {
        "prompt": "gato",
        "art_style": "realista",
        "color_palette": None,
        "composition": None,
        "dimensions": None,
        "negative_prompt": "sem texto",
    }


def test_same_vibe_reuses_style_changes_subject():
    """domain-model REQ-004: 'mesma vibe' mantém o estilo e troca o assunto."""
    base = ImageDesign(
        prompt="gato",
        style=DesignStyle(art_style="realista", dimensions="1:1"),
        negative_prompt="sem texto",
    )
    nd = same_vibe(base, "cachorro surfista")
    assert nd.prompt == "cachorro surfista"
    assert nd.style == base.style
    assert nd.negative_prompt == "sem texto"
    assert nd.references == ()


def test_same_vibe_propagates_references():
    """REQ-005: 'mesma vibe' pode carregar referências (ex.: imagem anterior)."""
    base = ImageDesign(prompt="gato", style=DesignStyle(art_style="realista"))
    ref = ImageReference(path="/out/prev.png")
    nd = same_vibe(base, "cachorro", references=[ref])
    assert nd.references == (ref,)
    assert nd.style == base.style


def test_merge_style_overrides_only_non_null():
    base = DesignStyle(art_style="realista", color_palette="azul", dimensions="1:1")
    merged = merge_style(base, DesignStyle(color_palette="tons quentes"))
    assert merged.art_style == "realista"
    assert merged.color_palette == "tons quentes"
    assert merged.dimensions == "1:1"


# --- consistent-imagery-generation REQ-001/REQ-002: imagens de referência ---


@pytest.mark.parametrize("bad", ["", "   ", None, 123])
def test_image_reference_requires_non_empty_path(bad):
    """REQ-002: ImageReference exige um path não vazio (VO puro, sem I/O)."""
    with pytest.raises(DomainError):
        ImageReference(path=bad)


def test_image_reference_strips_path():
    assert ImageReference(path="  /tmp/a.png ").path == "/tmp/a.png"


def test_image_design_defaults_to_no_references():
    """REQ-001: por padrão não há referências (geração text-only retrocompatível)."""
    d = ImageDesign(prompt="gato")
    assert d.references == ()
    assert d.has_references is False


def test_image_design_accepts_references_as_tuple():
    """REQ-001: referências informadas viram tupla imutável de ImageReference."""
    refs = [ImageReference(path="/tmp/a.png"), ImageReference(path="/tmp/b.png")]
    d = ImageDesign(prompt="gato", references=refs)
    assert d.references == (refs[0], refs[1])
    assert isinstance(d.references, tuple)
    assert d.has_references is True


def test_image_design_rejects_non_reference_items():
    """REQ-002: references só aceita objetos ImageReference."""
    with pytest.raises(DomainError):
        ImageDesign(prompt="gato", references=["/tmp/a.png"])


def test_image_design_metadata_ignores_references():
    """REQ-001: metadata() permanece estável — referências não poluem o sidecar."""
    d = ImageDesign(prompt="gato", references=[ImageReference(path="/tmp/a.png")])
    assert "references" not in d.metadata()
    assert set(d.metadata()) == {
        "prompt",
        "art_style",
        "color_palette",
        "composition",
        "dimensions",
        "negative_prompt",
    }
