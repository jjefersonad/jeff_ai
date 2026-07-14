"""`FallbackChatModel` — Ollama Cloud como primário, OpenRouter como fallback.

`create_deep_agent` chama `model.bind_tools(tools)` a cada turno (o conjunto de
tools varia por envelope — ver `src/agents/unified/envelope_middleware.py`), e
depois invoca o runnable resultante. Isso é o que torna `Runnable.with_fallbacks`
sozinho insuficiente aqui: ele devolve um `RunnableWithFallbacks` genérico, que
não implementa `bind_tools`. Este wrapper resolve isso fazendo o bind em CADA
sub-modelo primeiro, e só depois compondo o fallback — o padrão documentado do
LangChain para fallback + tool calling.

Falha no primário (rede, timeout, créditos esgotados no Ollama Cloud) cai para
o `openrouter_model` sem propagar a exceção ao grafo.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool

from src.models.ollama_model import ollama_model
from src.models.openrouter_model import openrouter_model


class FallbackChatModel(BaseChatModel):
    """Tenta `primary`; se falhar, tenta `fallback`.

    Ambos ficam disponíveis para `bind_tools` — a composição do fallback
    acontece DEPOIS do bind, não antes, para que o modelo retornado por
    `bind_tools` continue sendo um `Runnable` invocável normalmente pelo
    agent loop.
    """

    primary: BaseChatModel
    fallback: BaseChatModel

    @property
    def _llm_type(self) -> str:
        return "fallback-chat-model"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[Any, Any]:
        """Bind `tools` a cada sub-modelo e só então compõe o fallback."""
        bound_primary = self.primary.bind_tools(
            tools, tool_choice=tool_choice, **kwargs
        )
        bound_fallback = self.fallback.bind_tools(
            tools, tool_choice=tool_choice, **kwargs
        )
        return bound_primary.with_fallbacks([bound_fallback])

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        try:
            return self.primary._generate(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )
        except Exception:
            return self.fallback._generate(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        try:
            return await self.primary._agenerate(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )
        except Exception:
            return await self.fallback._agenerate(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )


unified_model = FallbackChatModel(primary=ollama_model, fallback=openrouter_model)

__all__ = ["FallbackChatModel", "unified_model"]
