"""Domínio de canais de chat: `ChannelKind`, `OutputAttachment`.

PURO: zero import de framework. Estes tipos são compartilhados por todos os
canais de entrega (web, Telegram, WhatsApp, Scheduled) e pelo `AgentRunOutcome`
(`application/ports/agent_runner.py`) — persistência, protocolo HTTP/Bot API
e I/O ficam em `infrastructure/`.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ChannelKind(str, Enum):
    """Canal de entrega de uma mensagem.

    `SCHEDULED` nunca é derivado de um `user_key` por prefixo (ver spec
    `user-integration-credentials` REQ-001) — só é usado pelo processo
    `jeff_cli` para registrar `ScheduledChannel` no `ChannelRegistry`.
    """

    WEB = "web"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    SCHEDULED = "scheduled"

    def __str__(self) -> str:  # noqa: D105 — usado em logs estruturados
        return f"ChannelKind.{self.name}"


@dataclass(frozen=True)
class OutputAttachment:
    """Um arquivo/mídia gerado pelo agente a ser entregue por um `ChatChannelPort`.

    `path` pode ser um filesystem path absoluto ou uma URL — o adapter de
    canal decide o que fazer com base em `mime` e no formato do próprio path.
    `url`, quando presente, é o endpoint HTTP servível já resolvido pela tool
    geradora (ex.: `generate_image_tool` devolve `{path, url, metadata}`) —
    usado por `WebChannel` para montar o evento SSE sem reconstruir rotas;
    Telegram/WhatsApp ignoram este campo (fazem upload via `path`).
    """

    path: str
    mime: str
    display_name: str
    url: str | None = None
