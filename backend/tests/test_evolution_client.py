"""Testes de `src/infrastructure/whatsapp/evolution_client.py`.

Cobre a task `whatsapp-evolution-channel-task-channel-1`:

- `parse_inbound_message()` extrai `phone_number` e `text` de um payload
  `messages.upsert` representativo da Evolution API.
- `bootstrap_config()` falha rápido, com mensagem clara citando todas as env
  vars faltantes de uma vez, quando `EVOLUTION_API_URL`/`EVOLUTION_API_KEY`/
  `EVOLUTION_INSTANCE_NAME` estão ausentes ou vazias — mesmo contrato de
  `telegram_gateway.bootstrap_config`.

Cobre a task `whatsapp-evolution-channel-task-tools-1`:

- `send_text(instance, phone_number, text)` monta e envia o `POST
  /message/sendText/{instance}` esperado pela Evolution API — verificado
  contra um transport HTTP mockado (`respx`), sem bater na rede real.
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from src.infrastructure.whatsapp import evolution_client


def _sample_messages_upsert_payload(
    *, text: str = "ola", from_me: bool = False
) -> dict[str, object]:
    """Payload representativo de um webhook `messages.upsert` da Evolution API."""
    return {
        "event": "messages.upsert",
        "instance": "jeff-ai-central",
        "data": {
            "key": {
                "remoteJid": "5511999998888@s.whatsapp.net",
                "fromMe": from_me,
                "id": "3EB0ABCDEF1234567890",
            },
            "pushName": "Jeferson",
            "message": {"conversation": text},
            "messageType": "conversation",
            "messageTimestamp": 1735689600,
        },
    }


def test_parse_inbound_message_extracts_phone_number_and_text() -> None:
    payload = _sample_messages_upsert_payload(text="123456")

    message = evolution_client.parse_inbound_message(payload)

    assert message is not None
    assert message.phone_number == "5511999998888"
    assert message.text == "123456"


def test_parse_inbound_message_returns_none_for_own_message() -> None:
    """Mensagens ecoadas pelo próprio número central (`fromMe=True`) são ignoradas."""
    payload = _sample_messages_upsert_payload(from_me=True)

    assert evolution_client.parse_inbound_message(payload) is None


def test_parse_inbound_message_returns_none_for_non_text_event() -> None:
    payload = {"event": "connection.update", "instance": "jeff-ai-central", "data": {}}

    assert evolution_client.parse_inbound_message(payload) is None


def test_bootstrap_config_raises_when_all_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EVOLUTION_API_URL", raising=False)
    monkeypatch.delenv("EVOLUTION_API_KEY", raising=False)
    monkeypatch.delenv("EVOLUTION_INSTANCE_NAME", raising=False)

    with pytest.raises(evolution_client.EvolutionConfigError) as exc_info:
        evolution_client.bootstrap_config()

    message = str(exc_info.value)
    assert "EVOLUTION_API_URL" in message
    assert "EVOLUTION_API_KEY" in message
    assert "EVOLUTION_INSTANCE_NAME" in message


def test_bootstrap_config_raises_when_one_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EVOLUTION_API_URL", "http://evolution_api:8080")
    monkeypatch.setenv("EVOLUTION_API_KEY", "fake-key")
    monkeypatch.delenv("EVOLUTION_INSTANCE_NAME", raising=False)

    with pytest.raises(evolution_client.EvolutionConfigError) as exc_info:
        evolution_client.bootstrap_config()

    message = str(exc_info.value)
    assert "EVOLUTION_INSTANCE_NAME" in message
    assert "EVOLUTION_API_URL" not in message


def test_bootstrap_config_rejects_empty_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EVOLUTION_API_URL", "")
    monkeypatch.setenv("EVOLUTION_API_KEY", "fake-key")
    monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "jeff-ai-central")

    with pytest.raises(evolution_client.EvolutionConfigError):
        evolution_client.bootstrap_config()


def test_bootstrap_config_returns_config_when_env_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EVOLUTION_API_URL", "http://evolution_api:8080")
    monkeypatch.setenv("EVOLUTION_API_KEY", "fake-key")
    monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "jeff-ai-central")
    monkeypatch.setenv("EVOLUTION_WEBHOOK_TOKEN", "fake-webhook-token")

    config = evolution_client.bootstrap_config()

    assert config.api_url == "http://evolution_api:8080"
    assert config.api_key == "fake-key"
    assert config.instance_name == "jeff-ai-central"
    assert config.webhook_token == "fake-webhook-token"


@respx.mock
async def test_send_text_posts_to_send_text_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """whatsapp-evolution-channel-task-tools-1-unit-1."""
    monkeypatch.setenv("EVOLUTION_API_URL", "http://evolution_api:8080")
    monkeypatch.setenv("EVOLUTION_API_KEY", "fake-key")
    monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "jeff-ai-central")
    monkeypatch.setenv("EVOLUTION_WEBHOOK_TOKEN", "fake-webhook-token")

    route = respx.post(
        "http://evolution_api:8080/message/sendText/jeff-ai-central"
    ).mock(return_value=httpx.Response(200, json={"key": {"id": "msg-1"}}))

    await evolution_client.send_text("jeff-ai-central", "5511999998888", "oi, tudo bem?")

    assert route.called
    request = route.calls[0].request
    body = json.loads(request.content)
    assert body["number"] == "5511999998888"
    assert body["text"] == "oi, tudo bem?"
    assert request.headers["apikey"] == "fake-key"


@respx.mock
async def test_send_image_posts_to_send_image_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unify-message-delivery-pipeline-task-adapters-2: `send_image` monta o POST
    esperado pela Evolution API para envio de mídia, com o mesmo contrato de
    fail-fast/`apikey` de `send_text`."""
    monkeypatch.setenv("EVOLUTION_API_URL", "http://evolution_api:8080")
    monkeypatch.setenv("EVOLUTION_API_KEY", "fake-key")
    monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "jeff-ai-central")
    monkeypatch.setenv("EVOLUTION_WEBHOOK_TOKEN", "fake-webhook-token")

    route = respx.post(
        "http://evolution_api:8080/message/sendImage/jeff-ai-central"
    ).mock(return_value=httpx.Response(200, json={"key": {"id": "msg-1"}}))

    await evolution_client.send_image(
        "jeff-ai-central", "5511999998888", "ZmFrZS1wbmc=", caption="olha só"
    )

    assert route.called
    request = route.calls[0].request
    body = json.loads(request.content)
    assert body["number"] == "5511999998888"
    assert body["mediatype"] == "image"
    assert body["media"] == "ZmFrZS1wbmc="
    assert body["caption"] == "olha só"
    assert request.headers["apikey"] == "fake-key"
