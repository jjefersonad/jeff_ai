"""Port de execução do agente + DTO `AgentRunResult`.

Abstrai como o agente `unified` é invocado fora de uma conversa HTTP
(subprocesso via `jeff_cli.py` no adapter). O DTO carrega só o que o
caller precisa saber — nenhum tipo do LangGraph vaza pra fora.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.domain.channels import OutputAttachment
from src.domain.scheduling import ToolScope


@dataclass(frozen=True)
class InterruptInfo:
    """Dados de um `__interrupt__` do LangGraph traduzidos para o port.

    O `HumanInTheLoopMiddleware` do LangChain pausa o grafo via
    `interrupt()` carregando um `HITLRequest` (lista de `ActionRequest` +
    lista de `ReviewConfig` do `langchain.agents.middleware`). Este DTO
    carrega essas duas listas como `tuple[dict, ...]` — serialização
    solta, deliberada: o port fica framework-agnostic (ver
    `clean-architecture`), sem importar tipos do LangGraph/LangChain.
    Consumidores (ex.: `telegram_gateway`) reconstroem/interpretam os
    campos conforme a necessidade (ex.: para renderizar botões inline
    baseando-se em `review_configs[i].allowed_decisions`).

    Attributes:
        action_requests: Um `ActionRequest` por item que precisa de
            aprovação. Serializado como `dict` (o `HITLRequest` original
            tem `name`/`args`/`description`, todos capturáveis).
        review_configs: Um `ReviewConfig` por item, no mesmo índice de
            `action_requests`. Traz `allowed_decisions` (subset de
            `{"approve", "edit", "reject"}`).
    """

    action_requests: tuple[dict, ...]
    review_configs: tuple[dict, ...]


@dataclass(frozen=True)
class AgentRunOutcome:
    """Output do agente capturado pelo `LangGraphDirectAgentRunner`.

    Definido pela spec `agent-output-capture`, para entrega via
    `ChatChannelPort`. `text` é o último `AIMessage` do turno (pode ser `None` para entregas
    puramente multimodais ou quando a captura não encontrou um `AIMessage`
    final). `attachments` são os arquivos gerados no turno atual — tupla
    vazia é válida.
    """

    text: str | None
    attachments: tuple[OutputAttachment, ...]


@dataclass(frozen=True)
class AgentRunResult:
    """Resultado de uma execução agendada do agente.

    `thread_id` é o thread que recebeu a execução; `status` é uma string
    livre (ex.: `"ok"`, `"error"`, `"timeout"`, `"interrupted"`) e
    `error` traz a mensagem descritiva em caso de falha — `None` em
    sucesso.

    `interrupt` é o campo aditivo introduzido pela change
    `telegram-tool-approval` para reportar que o grafo pausou num gate
    `interrupt_on` esperando decisão humana. Quando `status == "interrupted"`,
    `interrupt` traz os `action_requests`/`review_configs` necessários
    para apresentar a aprovação ao usuário; em qualquer outro `status`,
    `interrupt` é `None`. Default `None` preserva a assinatura dos
    call sites existentes (`RunScheduledTask`, `jeff_cli`, testes) sem
    precisar atualizá-los.

    `output` é o campo aditivo introduzido pela change
    `unify-message-delivery-pipeline` (spec `agent-runner` REQ-002):
    carrega o `AgentRunOutcome` capturado pelo `LangGraphDirectAgentRunner`
    em sucesso, para que `HandleChatMessage` entregue a resposta ao canal
    sem reconstruir estado do grafo. Default `None` preserva a assinatura
    de todo caller existente — nenhum precisa saber que este campo existe.
    """

    thread_id: str
    status: str
    error: str | None = None
    interrupt: InterruptInfo | None = None
    output: AgentRunOutcome | None = None


class AgentRunnerPort(ABC):
    """Invoca o agente `unified` com um único turno (sem chat ativa)."""

    @abstractmethod
    async def run(
        self,
        *,
        thread_id: str,
        prompt: str,
        skills: tuple[str, ...],
        tool_scope: ToolScope,
        user_key: str | None = None,
    ) -> AgentRunResult:
        """Executa um único turno do agente e devolve o resultado.

        Args:
            thread_id: Thread de destino (checkpointing compartilha com chat).
            prompt: Mensagem do usuário (instrução da tarefa agendada).
            skills: Skills extras a injetar (vazio = sem skills extras).
            tool_scope: Escopo de tools (RESTRICTED ou FULL — REQ-006).
            user_key: Identidade estável do canal (`telegram:<id>`,
                `web:<id>`). Opcional — ausente → gravador usa sentinel
                `unknown` (track-user-token-usage REQ-003).

        Returns:
            Resultado com thread_id/status/error.
        """
        raise NotImplementedError

    @abstractmethod
    async def resume(
        self,
        *,
        thread_id: str,
        decisions: tuple[dict, ...],
        user_key: str | None = None,
    ) -> AgentRunResult:
        """Resumir um grafo pausado por um gate `interrupt_on` com decisões humanas.

        Introduzido pela change `telegram-tool-approval` para que o
        `CallbackQueryHandler` do `telegram_gateway` consiga responder a
        aprovações sem importar tipos do LangGraph/LangChain (mantém o
        port framework-agnostic — ver `clean-architecture`).

        Args:
            thread_id: Thread pausada (recebida no `interrupt_info` do
                `run()` anterior).
            decisions: Tupla de `dict` representando as decisões
                humanas. Cada `dict` é um dos shapes aceitos pelo
                `HumanInTheLoopMiddleware` do LangChain
                (`{"type": "approve"}` ou `{"type": "reject", "message": ...}`).
            user_key: Mesma identidade do `run()` — propagada ao
                configurable para metering no resume
                (track-user-token-usage).

        Returns:
            `AgentRunResult` traduzido da resposta do grafo, com a
            MESMA semântica do `run()`: `status="ok"`, `"error"`, ou
            `"interrupted"` (segundo-round interrupt). A detecção de
            `__interrupt__` é a mesma de `run()`, garantindo que
            chamadas encadeadas (resume → interrupted → resume) sejam
            representáveis de forma uniforme.
        """
        raise NotImplementedError
