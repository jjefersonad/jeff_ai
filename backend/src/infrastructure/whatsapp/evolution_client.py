"""Cliente/bootstrap da Evolution API (canal WhatsApp, número central — Modelo B).

Responsabilidades cobertas por esta task (`whatsapp-evolution-channel-task-channel-1`):

- `bootstrap_config()` — lê e valida `EVOLUTION_API_URL`/`EVOLUTION_API_KEY`/
  `EVOLUTION_INSTANCE_NAME`/`EVOLUTION_WEBHOOK_TOKEN` do ambiente, falhando
  rápido (com mensagem citando todas as env vars faltantes de uma vez) antes
  de qualquer chamada HTTP. Mesmo contrato fail-fast de
  `telegram_gateway.bootstrap_config`. `EVOLUTION_WEBHOOK_TOKEN` foi
  adicionada depois (achado de teste manual, não fazia parte do escopo
  original desta task): sem ela, o webhook não tinha nenhum mecanismo de
  autenticação além do `require_auth` global — inviável para um chamador
  servidor-a-servidor sem cookie de sessão — nem validava a origem da
  chamada, permitindo forjar `phone_number` de qualquer usuário já vinculado.
- `parse_inbound_message()` — extrai `{phone_number, text}` de um payload de
  webhook `messages.upsert` da Evolution API.

Task `whatsapp-evolution-channel-task-tools-1`:

- `send_text(instance, phone_number, text)` — chama `POST
  /message/sendText/{instance}` da Evolution API com o payload mínimo
  `{"number": phone_number, "text": text}` e o header `apikey`. Usado tanto
  pelo tratamento de falha do canal (`whatsapp/authorization.py`,
  `task-channel-5`, REQ-006) quanto, futuramente, pela tool
  `send_whatsapp_message` (`whatsapp-tools`). Propaga `httpx.HTTPError` — cada
  chamador decide como tratar a falha (o canal absorve, a tool classifica em
  `error_kind`/`retryable`).

Task `whatsapp-evolution-channel-task-tools-3`:

- `classify_send_error(exc)` — classifica um `httpx.HTTPStatusError`
  levantado por `send_text` num resultado estruturado
  (`error_kind`/`retryable`), mesmo papel de
  `telegram/bot_client.classify_telegram_error` para o Telegram (REQ-003,
  whatsapp-tools-spec). A Evolution API em modo Cloud API repassa o corpo de
  erro da Graph API da Meta como está, então o código de erro (`error.code`)
  é o sinal primário; o HTTP status é o fallback quando o corpo não tem esse
  formato.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

_OUTSIDE_WINDOW_ERROR_CODES = {131047}
"""Códigos de erro da Cloud API para mensagem fora da janela de 24h
(re-engagement) sem template aprovado."""

_RATE_LIMIT_ERROR_CODES = {130429, 80007}
"""Códigos de erro da Cloud API para limite de mensagens/throughput
excedido."""


class EvolutionConfigError(RuntimeError):
    """Levantada quando `bootstrap_config` encontra configuração inválida."""


@dataclass(frozen=True)
class EvolutionConfig:
    """Configuração mínima lida do ambiente para falar com a Evolution API."""

    api_url: str
    api_key: str
    instance_name: str
    webhook_token: str


@dataclass(frozen=True)
class InboundMessage:
    """Mensagem de texto inbound já normalizada a partir do payload da Evolution API."""

    phone_number: str
    text: str


def _collect_missing_envs(names: tuple[str, ...]) -> list[str]:
    """Devolve os `names` cujo valor de ambiente está ausente ou vazio.

    Strings vazias são tratadas como ausentes — mesmo raciocínio de
    `telegram_gateway._collect_missing_envs`.
    """
    return [name for name in names if not os.environ.get(name)]


def bootstrap_config() -> EvolutionConfig:
    """Lê e valida as env vars obrigatórias. Falha rápido se faltar alguma.

    Lança `EvolutionConfigError` citando todas as env vars faltantes de uma
    vez, para o operador corrigir numa única passada.
    """
    missing = _collect_missing_envs(
        (
            "EVOLUTION_API_URL",
            "EVOLUTION_API_KEY",
            "EVOLUTION_INSTANCE_NAME",
            "EVOLUTION_WEBHOOK_TOKEN",
        )
    )

    if missing:
        env_list = ", ".join(missing)
        raise EvolutionConfigError(
            f"Configuração da Evolution API incompleta — faltando: {env_list}. "
            "Defina-as em ./.env (ou no ambiente do container) antes de "
            "iniciar o webhook do WhatsApp."
        )

    return EvolutionConfig(
        api_url=os.environ["EVOLUTION_API_URL"],
        api_key=os.environ["EVOLUTION_API_KEY"],
        instance_name=os.environ["EVOLUTION_INSTANCE_NAME"],
        webhook_token=os.environ["EVOLUTION_WEBHOOK_TOKEN"],
    )


def parse_inbound_message(payload: dict[str, object]) -> InboundMessage | None:
    """Extrai `{phone_number, text}` de um payload de webhook `messages.upsert`.

    Devolve `None` para eventos que não são `messages.upsert`, mensagens
    ecoadas pelo próprio número central (`key.fromMe=True` — a Evolution API
    reenvia as mensagens que ela mesma envia como eventos `messages.upsert`),
    ou mensagens sem texto (mídia sem legenda, reações, etc.) — nenhum desses
    casos deve chegar à resolução de autorização/roteamento.
    """
    if payload.get("event") != "messages.upsert":
        return None

    data = payload.get("data")
    if not isinstance(data, dict):
        return None

    key = data.get("key")
    if not isinstance(key, dict) or key.get("fromMe"):
        return None

    remote_jid = key.get("remoteJid")
    if not isinstance(remote_jid, str) or not remote_jid:
        return None
    phone_number = remote_jid.split("@", 1)[0]

    message = data.get("message")
    text = _extract_text(message) if isinstance(message, dict) else None
    if not text:
        return None

    return InboundMessage(phone_number=phone_number, text=text)


def _extract_text(message: dict[str, object]) -> str | None:
    """Extrai o texto de um objeto `message` da Evolution API.

    Cobre os dois formatos mais comuns de mensagem de texto: `conversation`
    (texto simples) e `extendedTextMessage.text` (texto com contexto, ex.:
    resposta a outra mensagem).
    """
    conversation = message.get("conversation")
    if isinstance(conversation, str) and conversation:
        return conversation

    extended = message.get("extendedTextMessage")
    if isinstance(extended, dict):
        text = extended.get("text")
        if isinstance(text, str) and text:
            return text

    return None


async def send_text(instance: str, phone_number: str, text: str) -> None:
    """Envia `text` a `phone_number` via `POST /message/sendText/{instance}`.

    Chama `bootstrap_config()` a cada envio (mesmo contrato fail-fast das
    demais funções deste módulo). Propaga `httpx.HTTPError` em vez de
    engolir — cada chamador decide como tratar a falha.
    """
    config = bootstrap_config()
    url = f"{config.api_url}/message/sendText/{instance}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            url,
            json={"number": phone_number, "text": text},
            headers={"apikey": config.api_key},
        )
        response.raise_for_status()


async def send_presence(
    instance: str,
    phone_number: str,
    *,
    presence: str = "composing",
    delay_ms: int = 5000,
) -> None:
    """Sinaliza presença (`composing`/`recording`) via `POST /chat/sendPresence/{instance}`.

    Contrato Evolution API v2.1.1 (typing-indicator-chat-channels Decision 6).
    Propaga `httpx.HTTPError` — o adapter engole, como em `send_text`.
    """
    config = bootstrap_config()
    url = f"{config.api_url}/chat/sendPresence/{instance}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            url,
            json={
                "number": phone_number,
                "options": {
                    "delay": delay_ms,
                    "presence": presence,
                    "number": phone_number,
                },
            },
            headers={"apikey": config.api_key},
        )
        response.raise_for_status()


async def send_media(
    instance: str,
    phone_number: str,
    media_url: str,
    *,
    mediatype: str,
    filename: str | None = None,
    caption: str | None = None,
) -> None:
    """Envia mídia (imagem ou documento) a `phone_number` via `POST /message/sendMedia/{instance}`.

    Endpoint unificado — `mediatype` ("image"/"document") é o discriminador.
    Confirmado ao vivo contra a instância real pinada (v2.1.1,
    `fix-whatsapp-document-delivery-task-adapters-1`): `/message/sendImage` e
    `/message/sendDocument` (endpoints per-tipo que este client chamava/teria
    chamado) não existem nesta instância (404) — `sendMedia` é o único real.
    `media_url` SHALL ser sempre uma URL: `media` em base64 retorna 500
    (`Cannot read properties of undefined (reading 'name')`) para qualquer
    `mediatype` nesta instância — verificado com um envio real. Mesmo contrato
    de `send_text`: chama `bootstrap_config()` a cada envio e propaga
    `httpx.HTTPError` em vez de engolir — o chamador (`WhatsAppChannel`)
    decide como tratar a falha via `classify_send_error`.
    """
    config = bootstrap_config()
    url = f"{config.api_url}/message/sendMedia/{instance}"
    payload: dict[str, Any] = {
        "number": phone_number,
        "mediatype": mediatype,
        "media": media_url,
    }
    if filename is not None:
        payload["fileName"] = filename
    if caption is not None:
        payload["caption"] = caption

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            url,
            json=payload,
            headers={"apikey": config.api_key},
        )
        response.raise_for_status()


async def send_buttons(
    instance: str,
    phone_number: str,
    *,
    title: str,
    description: str,
    buttons: list[dict[str, str]],
    footer: str | None = None,
) -> None:
    """Envia uma mensagem interativa com botões via `POST /message/sendButtons/{instance}`.

    Cada item de `buttons` segue `{"type": "reply", "id": ..., "text": ...}`
    — payload confirmado empiricamente contra a instância real pinada
    (`evoapicloud/evolution-api:v2.1.1`) no spike da task
    `whatsapp-tool-approval-task-spike-1` (2026-08-05): a API rejeita o
    formato `buttonId`/`buttonText.displayText` documentado publicamente
    para versões mais recentes, exigindo `type`/`id`/`text` diretos. Mesmo
    contrato de `send_text`/`send_media`: chama `bootstrap_config()` a cada
    envio e propaga `httpx.HTTPError` — o chamador (`WhatsAppChannel`)
    decide como tratar a falha (fallback para `send_text`, ver
    `whatsapp-tool-approval-design` Decision 1).
    """
    config = bootstrap_config()
    url = f"{config.api_url}/message/sendButtons/{instance}"
    payload: dict[str, Any] = {
        "number": phone_number,
        "title": title,
        "description": description,
        "buttons": buttons,
    }
    if footer is not None:
        payload["footer"] = footer

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            url,
            json=payload,
            headers={"apikey": config.api_key},
        )
        response.raise_for_status()


def classify_send_error(exc: httpx.HTTPStatusError) -> dict[str, Any]:
    """Classifica uma falha de `send_text` em resultado estruturado (REQ-003).

    Distingue a falha de janela de 24h expirada (`outside_window`, sem
    template aprovado) de rate limit transitório (`rate_limited`), com
    `forbidden`/`not_found` para outras falhas permanentes conhecidas e
    `transient` como fallback retryable — mesmo espírito de
    `telegram/bot_client.classify_telegram_error`.
    """
    code = _extract_error_code(exc.response)
    if code in _OUTSIDE_WINDOW_ERROR_CODES:
        return {
            "success": False,
            "error": str(exc),
            "error_kind": "outside_window",
            "retryable": False,
        }
    if code in _RATE_LIMIT_ERROR_CODES or exc.response.status_code == 429:
        return {
            "success": False,
            "error": str(exc),
            "error_kind": "rate_limited",
            "retryable": True,
        }
    if exc.response.status_code in (401, 403):
        return {
            "success": False,
            "error": str(exc),
            "error_kind": "forbidden",
            "retryable": False,
        }
    if exc.response.status_code == 404:
        return {
            "success": False,
            "error": str(exc),
            "error_kind": "not_found",
            "retryable": False,
        }
    return {
        "success": False,
        "error": str(exc),
        "error_kind": "transient",
        "retryable": True,
    }


def _extract_error_code(response: httpx.Response) -> int | None:
    """Extrai `error.code` (formato Graph API da Meta) do corpo da resposta.

    Devolve `None` quando o corpo não é JSON ou não tem o formato esperado
    — o chamador cai para o fallback por HTTP status.
    """
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None

    error = body.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        if isinstance(code, int):
            return code

    return None
