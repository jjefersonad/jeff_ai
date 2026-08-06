"""`ScheduledChannel` — adapter `ChatChannelPort` para o canal Scheduled.

Não fala com nenhum protocolo de saída próprio: resolve o `ChannelKind` do
owner a partir do `user_key` (formato `"<canal>:<id>"`) e delega a entrega
ao adapter concreto registrado no `ChannelRegistry` deste processo. Falha
alto — sem fallback silencioso — quando o canal não é resolvível ou não
está registrado (REQ-010 scheduled-tasks / REQ-004 chat-channel-port).
"""
from __future__ import annotations

from src.application.ports.agent_runner import InterruptInfo
from src.application.ports.chat_channel import ChatChannelPort, DeliveryKind
from src.domain.channels import ChannelKind, OutputAttachment
from src.infrastructure.channels.registry import ChannelRegistry
from src.infrastructure.usage.user_key import from_user_key


class ScheduledChannel(ChatChannelPort):
    """Adapter Scheduled — resolve e delega, nunca entrega diretamente."""

    @property
    def channel_kind(self) -> ChannelKind:
        """Sempre `ChannelKind.SCHEDULED` — usado por `ChannelRegistry.register`."""
        return ChannelKind.SCHEDULED

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
        """Resolve o canal primário do owner e delega a entrega a ele."""
        resolved_kind = from_user_key(user_key)
        if resolved_kind is None:
            raise RuntimeError("canal original do owner não está mais disponível")

        try:
            inner = ChannelRegistry.get(resolved_kind)
        except RuntimeError:
            raise RuntimeError(
                f"canal resolvido {resolved_kind.value} não está registrado neste processo"
            ) from None

        await inner.deliver(
            user_key=user_key,
            text=text,
            attachments=attachments,
            kind=kind,
            interrupt=interrupt,
            thread_id=thread_id,
        )

    async def start_typing_indicator(self, *, user_key: str) -> None:
        """No-op — o delegator não propaga typing ao canal interno (design OQ-2)."""
        return None

    async def stop_typing_indicator(self, *, user_key: str) -> None:
        """No-op — ver `start_typing_indicator`."""
        return None


__all__ = ["ScheduledChannel"]
