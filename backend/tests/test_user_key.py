"""Testes de `src.infrastructure.usage.user_key` (task `unify-message-delivery-pipeline-task-foundation-2`).

Verifica REQ-001 (user-integration-credentials): `from_user_key` deduz o
`ChannelKind` a partir do prefixo de um `user_key`, sem nunca levantar.
"""
from __future__ import annotations

import pytest

from src.domain.channels import ChannelKind
from src.infrastructure.usage.user_key import from_user_key


@pytest.mark.parametrize(
    ("user_key", "expected"),
    [
        ("web:8e3f4b1a-uuid", ChannelKind.WEB),
        ("telegram:123", ChannelKind.TELEGRAM),
        ("whatsapp:5511999998888", ChannelKind.WHATSAPP),
        (None, None),
        ("", None),
        ("unknown", None),
        ("unknown:foo", None),
    ],
)
def test_from_user_key_resolves_channel_by_prefix(user_key: str | None, expected: ChannelKind | None) -> None:
    assert from_user_key(user_key) is expected
