"""`WebChannel` — adapter `ChatChannelPort` para o canal web (SSE do frontend).

Não existe hoje um barramento SSE único no backend — o canal web historicamente
conversa direto com o LangGraph Platform (ver design
`unify-message-delivery-pipeline`, Context: "Web ... bypassa o port"). Este
adapter recebe `emit` (callable assíncrono) injetado como ponto de
integração com o que quer que sirva os eventos ao frontend — a fiação de
`emit` a um transporte real (SSE/WebSocket) é responsabilidade do
composition root, fora do escopo desta task.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from src.application.ports.agent_runner import InterruptInfo
from src.application.ports.chat_channel import ChatChannelPort, DeliveryKind
from src.domain.channels import ChannelKind, OutputAttachment

EmitEvent = Callable[[dict], Awaitable[None]]


class WebChannel(ChatChannelPort):
    """Adapter web — construtor recebe o `emit` (sink assíncrono de eventos SSE)."""

    def __init__(self, *, emit: EmitEvent) -> None:
        """Guarda `emit`, chamado uma vez por evento (texto, depois anexo)."""
        self._emit = emit

    @property
    def channel_kind(self) -> ChannelKind:
        """Sempre `ChannelKind.WEB` — usado por `ChannelRegistry.register`."""
        return ChannelKind.WEB

    async def deliver(
        self,
        *,
        user_key: str,
        text: str | None,
        attachments: tuple[OutputAttachment, ...],
        kind: DeliveryKind,
        interrupt: InterruptInfo | None = None,
        thread_id: str | None = None,
    ) -> None:
        """Emitir um evento de texto (se houver) seguido de um evento por anexo."""
        if text is not None:
            await self._emit({"kind": "text", "text": text})

        for attachment in attachments:
            event_kind = "image" if attachment.mime.startswith("image/") else "document"
            await self._emit(
                {
                    "kind": event_kind,
                    "url": attachment.url,
                    "display_name": attachment.display_name,
                }
            )


__all__ = ["WebChannel"]
