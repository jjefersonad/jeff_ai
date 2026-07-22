"""Testes de `attachment_context.extract_and_inject` (attachment-content-extraction REQ-001/REQ-004).

`_extract_text` (a chamada real ao `markitdown`) é monkeypatchada — este
módulo testa a LÓGICA de `extract_and_inject` (formatação, limite de
tamanho), não a extração em si, já delegada a uma biblioteca externa
confiável e usada da mesma forma por `read_document_tool.py`.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.infrastructure.attachments.store import StoredAttachment
from src.tools import attachment_context


def _attachment(**overrides: object) -> StoredAttachment:
    defaults: dict[str, object] = {
        "attachment_id": "att-1",
        "thread_id": "thread-1",
        "filename": "report.pdf",
        "content_type": "application/pdf",
        "size_bytes": 100,
        "storage_path": "/tmp/att-1.pdf",
    }
    defaults.update(overrides)
    return StoredAttachment(**defaults)  # type: ignore[arg-type]


def test_extract_and_inject_wraps_extracted_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """REQ-001: texto extraído vem embrulhado como "[Attachment: <filename>]\\n<texto>"."""
    monkeypatch.setattr(
        attachment_context, "_extract_text", lambda path: "Hello from the PDF."
    )

    result = attachment_context.extract_and_inject(_attachment())

    assert result == "[Attachment: report.pdf]\nHello from the PDF."


def test_extract_and_inject_truncates_over_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """REQ-004: texto acima do limite é truncado, com aviso anexado."""
    long_text = "x" * 100
    monkeypatch.setattr(attachment_context, "_extract_text", lambda path: long_text)

    result = attachment_context.extract_and_inject(_attachment(), max_chars=10)

    assert result.startswith("[Attachment: report.pdf]\n" + "x" * 10)
    assert "truncado" in result
    assert "x" * 11 not in result


def test_extract_and_inject_reads_from_storage_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """`_extract_text` recebe o `Path` resolvido de `storage_path`."""
    seen: dict[str, object] = {}

    def _fake_extract(path: object) -> str:
        seen["path"] = path
        return "content"

    monkeypatch.setattr(attachment_context, "_extract_text", _fake_extract)

    attachment_context.extract_and_inject(_attachment(storage_path="/tmp/xyz.pdf"))

    assert str(seen["path"]) == "/tmp/xyz.pdf"


def test_extract_and_inject_handles_extraction_failure_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-002: PDF corrompido/protegido não propaga exceção — devolve bloco de falha."""

    def _raise(path: object) -> str:
        raise ValueError("file has not been decrypted")

    monkeypatch.setattr(attachment_context, "_extract_text", _raise)

    result = attachment_context.extract_and_inject(_attachment(filename="secret.pdf"))

    assert (
        result
        == "[Attachment: secret.pdf — could not be read: file has not been decrypted]"
    )


def test_extract_and_inject_handles_empty_extracted_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-002: texto vazio (ex.: PDF escaneado sem OCR) também vira bloco de falha, não um bloco vazio silencioso."""
    monkeypatch.setattr(attachment_context, "_extract_text", lambda path: "   ")

    result = attachment_context.extract_and_inject(_attachment(filename="scan.pdf"))

    assert (
        result
        == "[Attachment: scan.pdf — could not be read: no extractable text found]"
    )


class _FakeModels:
    def __init__(self, response_text: str) -> None:
        self._response_text = response_text
        self.calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(text=self._response_text)


class _FakeGenaiClient:
    def __init__(self, response_text: str) -> None:
        self.models = _FakeModels(response_text)


def test_caption_image_returns_caption_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-003: com GOOGLE_API_KEY configurada, devolve a legenda do Gemini."""
    fake_client = _FakeGenaiClient("A photo of a cat sitting on a windowsill.")
    monkeypatch.setattr(
        attachment_context.genai, "Client", lambda api_key=None: fake_client
    )
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

    result = attachment_context.caption_image(b"fake-image-bytes", content_type="image/png")

    assert result == "A photo of a cat sitting on a windowsill."
    assert len(fake_client.models.calls) == 1


def test_caption_image_missing_key_returns_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-003: sem GOOGLE_API_KEY, não levanta — devolve a nota de fallback."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    result = attachment_context.caption_image(b"fake-image-bytes", content_type="image/png")

    assert result == "[Attachment: image — vision unavailable]"


def test_extract_and_inject_routes_image_attachments_to_caption_image(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """REQ-003: anexos image/* usam `caption_image`, não `_extract_text`."""
    image_path = tmp_path / "bike.png"
    image_path.write_bytes(b"fake-png-bytes")
    monkeypatch.setattr(
        attachment_context,
        "caption_image",
        lambda data, *, content_type: "A red bicycle leaning against a wall.",
    )

    result = attachment_context.extract_and_inject(
        _attachment(
            filename="bike.png",
            content_type="image/png",
            storage_path=str(image_path),
        )
    )

    assert result == "[Attachment: bike.png]\nA red bicycle leaning against a wall."


def test_extract_and_inject_reports_vision_unavailable_as_failure_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """REQ-003: fallback de `caption_image` vira bloco de falha com o filename real, sem duplicar o wrapper."""
    image_path = tmp_path / "bike.png"
    image_path.write_bytes(b"fake-png-bytes")
    monkeypatch.setattr(
        attachment_context,
        "caption_image",
        lambda data, *, content_type: attachment_context._VISION_UNAVAILABLE_NOTE,
    )

    result = attachment_context.extract_and_inject(
        _attachment(
            filename="bike.png",
            content_type="image/png",
            storage_path=str(image_path),
        )
    )

    assert result == "[Attachment: bike.png — could not be read: vision unavailable]"
