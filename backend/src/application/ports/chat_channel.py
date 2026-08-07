"""Port `ChatChannelPort` — o único caminho para entregar mensagens ao usuário.

Cada canal concreto (web, Telegram, WhatsApp, Scheduled) implementa este
port em `infrastructure/channels/`. O agente e o caso de uso
`HandleChatMessage` nunca conhecem o protocolo concreto de saída — falam
só com este port (ver design `unify-message-delivery-pipeline`, Decision
"ChatChannelPort é a única abstração de saída").
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from src.application.ports.agent_runner import InterruptInfo
from src.domain.channels import ChannelKind, OutputAttachment

DeliveryKind = Literal["normal", "failure", "interruption", "auto"]
"""Discrimina o que `deliver` deve entregar (spec `chat-channel-port` REQ-001):
`"normal"`/`"auto"` entregam `text`/`attachments`; `"failure"` substitui por
mensagem amigável do canal; `"interruption"` renderiza a aprovação usando
`interrupt`."""


class ChatChannelPort(ABC):
    """Contrato único de entrega — implementado por cada adapter de canal."""

    @property
    @abstractmethod
    def channel_kind(self) -> ChannelKind:
        """O `ChannelKind` deste adapter.

        Usado por `ChannelRegistry.register` para chavear o registro sem
        exigir um parâmetro `kind` explícito.
        """
        raise NotImplementedError

    @abstractmethod
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
        """Entrega uma mensagem ao usuário identificado por `user_key`.

        Args:
            user_key: Identidade estável do destinatário no formato
                `"<canal>:<id>"` (ex.: `"telegram:123"`).
            text: Texto da mensagem; pode ser `None` para entregas
                puramente multimodais.
            attachments: Arquivos/mídia gerados pelo agente neste turno.
            kind: Discrimina o tipo de entrega — ver `DeliveryKind`.
            interrupt: Presente quando `kind == "interruption"`; carrega
                os `action_requests`/`review_configs` para o adapter
                renderizar a aprovação (se o canal suportar).
            thread_id: Presente quando `kind == "interruption"`; alguns
                adapters (ex.: `TelegramChannel`) precisam associar a
                aprovação pendente a uma thread para o resume posterior.
                Default `None` — canais sem esse conceito o ignoram.
        """
        raise NotImplementedError

    @abstractmethod
    async def start_typing_indicator(self, *, user_key: str) -> None:
        """Sinaliza ao usuário que o agente está processando a mensagem.

        Contrato (design `typing-indicator-chat-channels`, Decision 1/6):
        idempotente — uma segunda chamada com o mesmo `user_key` enquanto a
        primeira ainda está ativa substitui (não empilha) o indicador; nunca
        propaga exceção — falhas do provedor (rate limit, timeout) são
        engolidas e logadas pelo próprio adapter. A orquestração de quando
        chamar este método (antes de `agent_runner.run(...)`, exceto no
        caminho `precomputed_output`) é responsabilidade de
        `HandleChatMessage.execute` — ver
        `typing-indicator-chat-channels-task-orchestration-1`.
        """
        raise NotImplementedError

    @abstractmethod
    async def stop_typing_indicator(self, *, user_key: str) -> None:
        """Encerra o indicador iniciado por `start_typing_indicator`.

        Contrato: MUST ser seguro chamar mesmo sem um `start` correspondente
        (idempotente) e nunca propaga exceção. Pensado para ser chamado pelo
        orquestrador em um bloco `finally` — ver nota em `start_typing_indicator`
        sobre o estado atual dessa wiring.
        """
        raise NotImplementedError
