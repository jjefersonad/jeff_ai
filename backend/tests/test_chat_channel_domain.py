"""Testes dos tipos puros de domínio para canais de chat (task `unify-message-delivery-pipeline-task-foundation-1`).

Puro: sem framework, sem I/O. Verifica:
- REQ-002 (user-integration-credentials): `ChannelKind` tem exatamente 4 membros e serializa
  como `"ChannelKind.<NOME>"` em `str()` (usado em logs estruturados).
- REQ-004 (agent-runner): `OutputAttachment` é um frozen dataclass com `path`/`mime`/`display_name`.
"""
from __future__ import annotations

import dataclasses

import pytest

from src.domain.channels.chat_channel import ChannelKind, OutputAttachment


def test_channel_kind_has_exactly_four_members() -> None:
    assert {member.name for member in ChannelKind} == {"WEB", "TELEGRAM", "WHATSAPP", "SCHEDULED"}


def test_channel_kind_str_uses_default_enum_mixin() -> None:
    assert str(ChannelKind.TELEGRAM) == "ChannelKind.TELEGRAM"


def test_output_attachment_constructs_with_required_fields() -> None:
    attachment = OutputAttachment(path="outputs/foo.png", mime="image/png", display_name="foo.png")

    assert attachment.path == "outputs/foo.png"
    assert attachment.mime == "image/png"
    assert attachment.display_name == "foo.png"


def test_output_attachment_is_frozen() -> None:
    attachment = OutputAttachment(path="outputs/foo.png", mime="image/png", display_name="foo.png")

    with pytest.raises(dataclasses.FrozenInstanceError):
        attachment.path = "outputs/other.png"  # type: ignore[misc]


def test_output_attachment_url_defaults_to_none() -> None:
    attachment = OutputAttachment(path="outputs/foo.png", mime="image/png", display_name="foo.png")

    assert attachment.url is None


def test_output_attachment_url_can_be_set() -> None:
    attachment = OutputAttachment(
        path="outputs/foo.png", mime="image/png", display_name="foo.png", url="/api/files/images/foo.png"
    )

    assert attachment.url == "/api/files/images/foo.png"
