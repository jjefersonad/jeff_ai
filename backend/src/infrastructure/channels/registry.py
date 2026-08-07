"""`ChannelRegistry` — registro por processo dos adapters `ChatChannelPort`.

Vive como estado de classe (não instância) porque é populado UMA vez pelo
composition root de cada processo (webapp registra web+telegram+whatsapp;
`jeff_cli` registra só scheduled — spec `chat-channel-port` REQ-002) e lido
por qualquer código do mesmo processo depois disso, sem precisar passar a
instância do registry adiante.
"""
from __future__ import annotations

from typing import ClassVar

from src.application.ports.chat_channel import ChatChannelPort
from src.domain.channels import ChannelKind


class ChannelRegistry:
    """Registro module/process-level de adapters `ChatChannelPort` por `ChannelKind`."""

    _adapters: ClassVar[dict[ChannelKind, ChatChannelPort]] = {}

    @classmethod
    def register(cls, adapter: ChatChannelPort) -> None:
        """Registra `adapter`, chaveado pelo seu próprio `channel_kind`."""
        cls._adapters[adapter.channel_kind] = adapter

    @classmethod
    def get(cls, kind: ChannelKind) -> ChatChannelPort:
        """Retorna o adapter registrado para `kind`.

        Levanta `RuntimeError` se nenhum adapter foi registrado para esse
        canal neste processo — sem fallback silencioso (REQ-002).
        """
        try:
            return cls._adapters[kind]
        except KeyError:
            raise RuntimeError(f"canal {kind.value} não registrado neste processo") from None

    @classmethod
    def reset(cls) -> None:
        """Limpa o registro — uso exclusivo de testes (isolamento entre casos)."""
        cls._adapters.clear()
