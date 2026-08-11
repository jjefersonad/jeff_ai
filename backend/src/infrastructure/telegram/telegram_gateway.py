"""Gateway do canal Telegram (processo próprio de longa duração).

Responsabilidades:

- Carregar `TELEGRAM_BOT_TOKEN` e `TELEGRAM_AUTHORIZED_CHAT_ID` do ambiente.
- Falhar rápido (com mensagem clara citando as env vars faltantes) antes de
  iniciar o polling, se alguma delas estiver ausente ou vazia.
- Construir o `LangGraphDirectAgentRunner` reaproveitando `build_unified()`
  de `src/agents/unified/agent.py` — SEM duplicar a fábrica do grafo.
- Garantir o schema do mapeamento `chat_id → thread_id`
  (`ensure_telegram_threads_schema`), o schema aditivo do checkpointer
  LangGraph (`ensure_langgraph_checkpoint_schema`) e abrir o pool Postgres
  que o `LangGraphDirectAgentRunner` usará por `run()`.
- Registrar o `MessageHandler` (`authorization.make_message_handler`,
  filtro `filters.TEXT & ~filters.COMMAND`), o `CommandHandler`
  (`commands.make_command_dispatcher`, comandos `new`/`title`/`resume`/
  `sessions`) e o `CallbackQueryHandler` (`approval.make_approval_callback_handler`,
  para os botões Aprovar/Editar/Rejeitar) na `Application` antes de
  iniciar o polling (`telegram-slash-commands-task-gateway-1`,
  `telegram-tool-approval-task-gateway-5`).
- Iniciar o loop de long-polling do `python-telegram-bot`.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Protocol

from src.composition.env import load_env

logger = logging.getLogger(__name__)


class TelegramConfigError(RuntimeError):
    """Levantada quando o `bootstrap_config` encontra configuração inválida."""


@dataclass(frozen=True)
class TelegramConfig:
    """Configuração mínima lida do ambiente para o gateway subir."""

    bot_token: str
    authorized_chat_id: str


def _collect_missing_envs(names: tuple[str, ...]) -> list[str]:
    """Devolve a lista de `names` cujo valor de ambiente está ausente ou vazio.

    Strings vazias são tratadas como ausentes — a env var declarada sem
    valor não é configuração válida para o `Bot(token=...)` do
    `python-telegram-bot`, que levantaria `InvalidToken` se chamado com "".
    """
    return [name for name in names if not os.environ.get(name)]


def bootstrap_config() -> TelegramConfig:
    """Lê e valida as env vars obrigatórias. Falha rápido se faltar alguma.

    Lança `TelegramConfigError` (nunca uma exceção genérica) com mensagem
    citando todas as env vars faltantes de uma vez, para o operador corrigir
    numa única passada. Strings vazias são tratadas como ausentes — a env var
    declarada sem valor não é configuração válida.
    """
    missing = _collect_missing_envs(
        ("TELEGRAM_BOT_TOKEN", "TELEGRAM_AUTHORIZED_CHAT_ID")
    )

    if missing:
        env_list = ", ".join(missing)
        raise TelegramConfigError(
            f"Configuração do gateway Telegram incompleta — faltando: {env_list}. "
            "Defina-as em ./.env antes de iniciar o telegram_gateway."
        )

    return TelegramConfig(
        bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        authorized_chat_id=os.environ["TELEGRAM_AUTHORIZED_CHAT_ID"],
    )


class _PollingApplication(Protocol):
    """Tipo estrutural mínimo exigido pelo gateway.

    `bot` é usado para fechar `make_message_handler`/`make_command_dispatcher`
    sobre a instância real de `telegram.Bot` que a própria `Application`
    constrói a partir do token — evita que `main()` precise instanciar um
    `Bot` separado.
    """

    bot: object

    def run_polling(self, *args: object, **kwargs: object) -> None: ...
    def add_handler(self, handler: object, *args: object, **kwargs: object) -> None: ...


def build_application(config: TelegramConfig) -> _PollingApplication:
    """Monta a `Application` do `python-telegram-bot` com o token configurado.

    Função extraída de `main()` para ser substituível em testes (a task
    `task-channel-1-unit-1` substitui esse símbolo via `monkeypatch` para
    verificar que `main()` NÃO chama `run_polling()` quando o bootstrap
    falha).
    """
    # Importação lazy: deps pesadas (python-telegram-bot) só são carregadas
    # depois do bootstrap ter passado, para falhar rápido sem custo de import.
    from telegram.ext import ApplicationBuilder  # noqa: I001

    return ApplicationBuilder().token(config.bot_token).build()


def build_runner(*, postgres_uri: str):
    """Constrói o `LangGraphDirectAgentRunner` reaproveitando `build_unified`.

    Importação lazy dos módulos do LangGraph/Postgres para que um bootstrap
    que falha por env vars não gaste tempo nem memória importando a stack
    inteira do grafo antes de sair.
    """
    from src.infrastructure.agent_runtime.langgraph_direct_runner import (
        LangGraphDirectAgentRunner,
    )

    return LangGraphDirectAgentRunner(postgres_uri=postgres_uri)


def main() -> int:
    """Entry-point do processo `telegram_gateway`.

    Ordem deliberada:
    1. `load_env()` — carrega apenas `./.env` (raiz do repositório).
    2. `bootstrap_config()` — falha rápido se faltarem env vars (NÃO chama
       `run_polling`).
    3. `ensure_telegram_threads_schema()` — DDL idempotente.
    4. `usage.ensure_schema()` — tabela `token_usage_events` (metering).
    5. `ensure_langgraph_checkpoint_schema()` — ALTER aditivo do checkpointer
       (ex.: `task_path`); fail-fast se falhar.
    6. `build_runner()` — constrói o adapter (reusa `build_unified`).
    7. `build_application()` — registra `MessageHandler` (mensagens normais)
       e `CommandHandler` (`/new`, `/title`, `/resume`, `/sessions`).
    8. `application.run_polling()` — só aqui o loop infinito inicia.

    Retorna 0 em saída por Ctrl-C limpo e != 0 em qualquer falha de
    bootstrap. Exceções não-tratadas durante o polling são logadas e
    propagadas (o supervisor externo cuida do restart).
    """
    load_env()

    try:
        config = bootstrap_config()
    except TelegramConfigError as exc:
        logger.error("%s", exc)
        return 1

    postgres_uri = os.environ.get("POSTGRES_URI")
    if not postgres_uri:
        logger.error(
            "POSTGRES_URI não está configurado (esperada em ./.env)."
        )
        return 1

    # Importação lazy: as deps pesadas (LangGraph, Postgres drivers,
    # python-telegram-bot) só são carregadas depois do bootstrap ter
    # passado.
    from telegram.ext import CommandHandler, MessageHandler, filters

    from src.application.use_cases.redeem_telegram_link_code import (
        RedeemTelegramLinkCode,
    )
    from src.infrastructure.agent_runtime.checkpoint_schema import (
        ensure_langgraph_checkpoint_schema,
    )
    from src.infrastructure.persistence import (
        telegram_link_codes_schema,
        user_integrations_schema,
    )
    from src.infrastructure.persistence.telegram_link_codes_repository import (
        PostgresTelegramLinkCodeRepository,
    )
    from src.infrastructure.persistence.user_integrations_repository import (
        PostgresUserIntegrationRepository,
    )
    from src.infrastructure.telegram.approval import make_approval_callback_handler
    from src.infrastructure.telegram.authorization import make_message_handler
    from src.infrastructure.telegram.commands import make_command_dispatcher
    from src.infrastructure.telegram.schema import ensure_telegram_threads_schema
    from src.infrastructure.telegram.start_command import make_start_command_handler
    from src.infrastructure.usage import schema as usage_schema

    ensure_telegram_threads_schema(postgres_uri)
    # Mesma tabela que o lifespan do webapp — o gateway grava usage offline
    # do HTTP e precisa do schema antes do primeiro record do DirectRunner.
    usage_schema.ensure_schema(postgres_uri)
    # Schema UUID legado do LangGraph API pode faltar colunas aditivas
    # (`task_path`). Fail-fast aqui — nunca iniciar polling sem o DDL.
    ensure_langgraph_checkpoint_schema(postgres_uri)
    # `/start <code>` (account linking) precisa das duas tabelas abaixo.
    # O lifespan do webapp já garante esse schema, mas o gateway é um
    # processo separado que pode subir antes/independente dele — mesmo
    # raciocínio fail-fast dos três `ensure_*` acima (channel-link-wiring
    # Decision 1).
    telegram_link_codes_schema.ensure_schema(postgres_uri)
    user_integrations_schema.ensure_schema(postgres_uri)
    runner = build_runner(postgres_uri=postgres_uri)

    application = build_application(config)
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            make_message_handler(
                authorized_chat_id=config.authorized_chat_id,
                agent_runner=runner,
                bot=application.bot,
            ),
        )
    )
    application.add_handler(
        CommandHandler(
            ["new", "title", "resume", "sessions"],
            make_command_dispatcher(
                authorized_chat_id=config.authorized_chat_id,
                bot=application.bot,
            ),
        )
    )
    # `/start <code>` NÃO aplica `is_authorized_chat` (ver docstring de
    # `start_command.py`) — o próprio propósito é vincular um chat_id ainda
    # não autorizado. Registrado como `CommandHandler` próprio, não misturado
    # ao dispatcher de `new/title/resume/sessions` (que exige autorização).
    application.add_handler(
        CommandHandler(
            ["start"],
            make_start_command_handler(
                redeem_use_case=RedeemTelegramLinkCode(
                    link_code_repository=PostgresTelegramLinkCodeRepository(postgres_uri),
                    user_integration_repository=PostgresUserIntegrationRepository(
                        postgres_uri
                    ),
                ),
                bot=application.bot,
            ),
        )
    )
    # `CallbackQueryHandler` por ÚLTIMO (após `MessageHandler` e
    # `CommandHandler`) — handler ordering: `CommandHandler` →
    # `MessageHandler` → `CallbackQueryHandler`, a mesma ordem usada
    # pelos exemplos de `python-telegram-bot` para slash commands +
    # texto livre + botões. Mudar essa ordem é um handler-order
    # invariant documentado em
    # `telegram-tool-approval-task-gateway-5-unit-1` (REQs 002/003).
    application.add_handler(
        make_approval_callback_handler(
            authorized_chat_id=config.authorized_chat_id,
            agent_runner=runner,
            bot=application.bot,
        )
    )
    logger.info(
        "telegram_gateway iniciado; chat_id autorizado=%s",
        config.authorized_chat_id,
    )
    application.run_polling()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
