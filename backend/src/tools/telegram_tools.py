"""Tools de envio ativo para o canal Telegram.

Validador de path compartilhado pelas tools de envio (`send_telegram_photo`,
`send_telegram_document`): garante que qualquer arquivo enviado ao Telegram
resida dentro de `backend/outputs/`, mesma allowlist de raiz usada por
`documents_router.py`/`images_router.py`.

`send_telegram_message` é wrapper deprecated (cleanup-1): permanece
importável para skills/scripts externos, mas não está em `_UNIFIED_TOOLS`.
Delega a `ChannelRegistry` → `TelegramChannel.deliver`.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from langchain_core.tools import tool
from telegram import Bot

from src.domain.channels import ChannelKind
from src.infrastructure.channels.registry import ChannelRegistry
from src.infrastructure.telegram import bot_client
from src.infrastructure.usage.user_key import telegram_user_key

logger = logging.getLogger(__name__)

# backend/outputs (backend/src/tools/telegram_tools.py -> parents[2] == backend).
_ALLOWED_OUTPUTS_ROOT = Path(__file__).resolve().parents[2] / "outputs"


class TelegramPathNotAllowedError(ValueError):
    """Levantada quando um path de envio resolve para fora de backend/outputs/."""


def _resolve_allowed_output_path(path: str) -> Path:
    """Canonicaliza `path` e garante que está dentro de `backend/outputs/`.

    Levanta `TelegramPathNotAllowedError` (nunca uma exceção não tratada) se o
    path resolvido — após canonicalização via `realpath`, cobrindo `../` e
    symlinks — cair fora da allowlist de raiz.
    """
    try:
        resolved = Path(path).resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise TelegramPathNotAllowedError(f"Path inválido: {path}") from exc

    allowed_root = _ALLOWED_OUTPUTS_ROOT.resolve()
    if resolved != allowed_root and allowed_root not in resolved.parents:
        raise TelegramPathNotAllowedError(
            f"Path fora do diretório permitido (backend/outputs/): {path}"
        )
    return resolved


def _path_not_allowed_result(exc: TelegramPathNotAllowedError) -> dict[str, Any]:
    """Constrói o resultado estruturado de falha permanente (`bad_format`, não retentável).

    Aplica-se a partir de uma `TelegramPathNotAllowedError` — REQ-004 e
    REQ-005 (telegram-tools-spec).
    """
    return {
        "success": False,
        "error": str(exc),
        "error_kind": "bad_format",
        "retryable": False,
    }


@tool
async def send_telegram_message(text: str, chat_id: str | None = None) -> dict[str, Any]:
    """Envia uma mensagem de texto para um chat do Telegram.

    .. deprecated::
        Use `send_message` (canal-agnóstica) ou o pipeline
        `HandleChatMessage`. Este wrapper permanece por uma release para
        skills/scripts que ainda importam a tool diretamente.

    Quando `chat_id` não é informado, usa `TELEGRAM_AUTHORIZED_CHAT_ID` como
    destino padrão. Delega a `TelegramChannel.deliver` via `ChannelRegistry`.
    """
    logger.warning(
        "send_telegram_message is deprecated; use send_message. "
        "Will be removed after callers migrate to HandleChatMessage."
    )
    target_chat_id = chat_id or os.environ["TELEGRAM_AUTHORIZED_CHAT_ID"]
    channel = ChannelRegistry.get(ChannelKind.TELEGRAM)
    await channel.deliver(
        user_key=telegram_user_key(target_chat_id),
        text=text,
        attachments=(),
        kind="normal",
    )
    return {"success": True}


@tool
async def send_telegram_photo(
    path: str, chat_id: str | None = None, caption: str | None = None
) -> dict[str, Any]:
    """Envia uma foto para um chat do Telegram a partir de um path local.

    Aceita diretamente o `path` retornado por `create_image_from_prompt`
    (REQ-003, telegram-tools-spec). O `path` é validado contra a allowlist
    de raiz `backend/outputs/` antes de qualquer I/O — paths rejeitados não
    geram chamada à Bot API (REQ-004). Quando `chat_id` não é informado, usa
    `TELEGRAM_AUTHORIZED_CHAT_ID` como destino padrão (REQ-002).
    """
    try:
        resolved = _resolve_allowed_output_path(path)
    except TelegramPathNotAllowedError as exc:
        return _path_not_allowed_result(exc)

    photo_bytes = resolved.read_bytes()
    target_chat_id = chat_id or os.environ["TELEGRAM_AUTHORIZED_CHAT_ID"]
    bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])

    return await bot_client.call_bot_api(
        lambda: bot.send_photo(chat_id=target_chat_id, photo=photo_bytes, caption=caption)
    )


@tool
async def send_telegram_document(
    path: str, chat_id: str | None = None, caption: str | None = None
) -> dict[str, Any]:
    """Envia um documento para um chat do Telegram a partir de um path local.

    Aceita diretamente o `path` retornado por `create_docx_document`,
    `create_xlsx_spreadsheet` e `create_pptx_presentation` (REQ-003,
    telegram-tools-spec). O `path` é validado contra a allowlist de raiz
    `backend/outputs/` antes de qualquer I/O — paths rejeitados não geram
    chamada à Bot API (REQ-004). Quando `chat_id` não é informado, usa
    `TELEGRAM_AUTHORIZED_CHAT_ID` como destino padrão (REQ-002).
    """
    try:
        resolved = _resolve_allowed_output_path(path)
    except TelegramPathNotAllowedError as exc:
        return _path_not_allowed_result(exc)

    document_bytes = resolved.read_bytes()
    target_chat_id = chat_id or os.environ["TELEGRAM_AUTHORIZED_CHAT_ID"]
    bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])

    return await bot_client.call_bot_api(
        lambda: bot.send_document(
            chat_id=target_chat_id,
            document=document_bytes,
            filename=resolved.name,
            caption=caption,
        )
    )
