"""Domínio de canais de chat — tipos puros compartilhados por todos os adapters.

PURO: zero import de framework. Toda regra de negócio sobre o que é um
`ChannelKind` e um `OutputAttachment` vive aqui; protocolo HTTP/Bot API,
persistência e I/O ficam em `infrastructure/`.
"""
from src.domain.channels.chat_channel import ChannelKind, OutputAttachment

__all__ = ["ChannelKind", "OutputAttachment"]
