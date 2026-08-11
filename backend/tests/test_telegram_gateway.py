"""Testes do entrypoint `src/infrastructure/telegram/telegram_gateway.py`.

Cobre a task `integracao-telegram-task-channel-1`:

- `bootstrap_config()` falha rápido (antes de iniciar o polling) com uma
  mensagem clara quando `TELEGRAM_BOT_TOKEN` ou `TELEGRAM_AUTHORIZED_CHAT_ID`
  não estão configurados.
- `bootstrap_config()` devolve um dataclass com os valores lidos do ambiente
  quando ambos estão presentes.
- `main()` não invoca o `Application.run_polling()` quando o bootstrap falha
  (o polling nunca chega a iniciar — proteção em profundidade).

Cobre também a task `telegram-slash-commands-task-gateway-1`:

- `main()` registra um `MessageHandler` (filtro `filters.TEXT & ~filters.COMMAND`)
  e um `CommandHandler` (`["new", "title", "resume", "sessions"]`) na
  `Application` antes de `run_polling()` (REQ-009).
- O filtro do `MessageHandler` rejeita slash commands e aceita mensagens
  normais; o `CommandHandler` rejeita mensagens normais (REQ-010).
"""
from __future__ import annotations

import datetime
import importlib
from typing import Any

import pytest
from telegram import Chat, Message, MessageEntity, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters

from src.application.use_cases.redeem_telegram_link_code import RedeemTelegramLinkCode
from src.infrastructure.telegram import approval as telegram_approval
from src.infrastructure.telegram import schema as telegram_schema
from src.infrastructure.telegram import start_command as telegram_start_command
from src.infrastructure.telegram import telegram_gateway
from src.infrastructure.usage import schema as usage_schema


def _make_update(text: str, *, is_command: bool) -> Update:
    """Constrói um `Update` real com `Message` mínima para exercitar filtros.

    `is_command=True` adiciona a `MessageEntity` de `bot_command` no offset 0,
    que é o que `filters.COMMAND` e `CommandHandler.check_update` inspecionam
    — sem ela, um texto começando com "/" não seria reconhecido como comando
    (o Telegram real também não reconheceria).
    """
    chat = Chat(id=123, type="private")
    entities = (
        [MessageEntity(type=MessageEntity.BOT_COMMAND, offset=0, length=len(text.split()[0]))]
        if is_command
        else []
    )
    message = Message(
        message_id=1,
        date=datetime.datetime.now(datetime.timezone.utc),
        chat=chat,
        text=text,
        entities=entities,
    )
    return Update(update_id=1, message=message)


class _RecordingPollingApp:
    """Captura o `run_polling()` para garantir que NUNCA é chamado em falha de bootstrap."""

    def __init__(self) -> None:
        self.run_polling_called = False

    def run_polling(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        self.run_polling_called = True


def test_bootstrap_config_raises_when_token_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falta `TELEGRAM_BOT_TOKEN` → erro claro citando a env var faltante."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_AUTHORIZED_CHAT_ID", "123456")

    with pytest.raises(telegram_gateway.TelegramConfigError) as exc_info:
        telegram_gateway.bootstrap_config()

    message = str(exc_info.value)
    assert "TELEGRAM_BOT_TOKEN" in message


def test_bootstrap_config_raises_when_chat_id_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falta `TELEGRAM_AUTHORIZED_CHAT_ID` → erro claro citando a env var faltante."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.delenv("TELEGRAM_AUTHORIZED_CHAT_ID", raising=False)

    with pytest.raises(telegram_gateway.TelegramConfigError) as exc_info:
        telegram_gateway.bootstrap_config()

    message = str(exc_info.value)
    assert "TELEGRAM_AUTHORIZED_CHAT_ID" in message


def test_bootstrap_config_raises_when_both_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Faltam ambas → erro cita as duas para o usuário corrigir de uma vez."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_AUTHORIZED_CHAT_ID", raising=False)

    with pytest.raises(telegram_gateway.TelegramConfigError) as exc_info:
        telegram_gateway.bootstrap_config()

    message = str(exc_info.value)
    assert "TELEGRAM_BOT_TOKEN" in message
    assert "TELEGRAM_AUTHORIZED_CHAT_ID" in message


def test_bootstrap_config_returns_config_when_env_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Com as duas env vars presentes, devolve um `TelegramConfig` com os valores lidos."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token-abc")
    monkeypatch.setenv("TELEGRAM_AUTHORIZED_CHAT_ID", "999")

    config = telegram_gateway.bootstrap_config()

    assert config.bot_token == "fake-token-abc"
    assert config.authorized_chat_id == "999"


def test_bootstrap_config_rejects_empty_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`TELEGRAM_BOT_TOKEN=""` é tratado como ausente (string vazia não conta)."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_AUTHORIZED_CHAT_ID", "123")

    with pytest.raises(telegram_gateway.TelegramConfigError):
        telegram_gateway.bootstrap_config()


def test_main_does_not_start_polling_when_bootstrap_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mesmo se `main()` for invocado direto, polling NÃO inicia se o bootstrap falha.

    Garante a propriedade "falha antes de iniciar o polling" no nível do
    `main()`, independente de como o bootstrap é chamado.
    """
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_AUTHORIZED_CHAT_ID", raising=False)
    # main() chama load_env() — sem isso, ./.env reporia as vars.
    monkeypatch.setattr(telegram_gateway, "load_env", lambda: None)

    recording_app = _RecordingPollingApp()
    monkeypatch.setattr(
        telegram_gateway, "build_application", lambda _cfg: recording_app
    )

    exit_code = telegram_gateway.main()

    assert exit_code != 0
    assert recording_app.run_polling_called is False, (
        "main() NÃO pode chamar run_polling() quando o bootstrap falha — "
        "esse é o ponto da guard clause."
    )


def test_module_exposes_required_symbols() -> None:
    """O módulo exporta `bootstrap_config`, `TelegramConfig`, `TelegramConfigError`, `main`."""
    # Reimporta pra garantir que pegamos o estado mais recente.
    module = importlib.reload(telegram_gateway)
    assert hasattr(module, "bootstrap_config")
    assert hasattr(module, "TelegramConfig")
    assert hasattr(module, "TelegramConfigError")
    assert hasattr(module, "main")
    assert hasattr(module, "build_application")


class _RecordingApplication:
    """Fake `Application` que grava os handlers passados a `add_handler`."""

    def __init__(self) -> None:
        self.handlers: list[Any] = []
        self.run_polling_called = False
        self.bot = object()

    def add_handler(self, handler: Any, *args: Any, **kwargs: Any) -> None:
        self.handlers.append(handler)

    def run_polling(self, *args: Any, **kwargs: Any) -> None:
        self.run_polling_called = True


def test_main_registers_message_and_command_handlers_before_polling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-009 cenário "Gateway sobe com handlers registrados".

    Após o bootstrap terminar, a `Application` recebeu pelo menos um
    `MessageHandler` (filtro `filters.TEXT & ~filters.COMMAND`) e um
    `CommandHandler` (`["new", "title", "resume", "sessions"]`) — ambos
    antes de `run_polling()` ser chamado.
    """
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_AUTHORIZED_CHAT_ID", "123")
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    monkeypatch.setattr(telegram_schema, "ensure_telegram_threads_schema", lambda uri: None)
    monkeypatch.setattr(usage_schema, "ensure_schema", lambda uri: None)
    monkeypatch.setattr(
        "src.infrastructure.agent_runtime.checkpoint_schema.ensure_langgraph_checkpoint_schema",
        lambda uri: None,
    )
    monkeypatch.setattr(
        "src.infrastructure.persistence.telegram_link_codes_schema.ensure_schema",
        lambda uri: None,
    )
    monkeypatch.setattr(
        "src.infrastructure.persistence.user_integrations_schema.ensure_schema",
        lambda uri: None,
    )
    monkeypatch.setattr(telegram_gateway, "build_runner", lambda *, postgres_uri: object())

    recording_app = _RecordingApplication()
    monkeypatch.setattr(telegram_gateway, "build_application", lambda _cfg: recording_app)

    exit_code = telegram_gateway.main()

    assert exit_code == 0
    assert recording_app.run_polling_called is True

    message_handlers = [h for h in recording_app.handlers if isinstance(h, MessageHandler)]
    command_handlers = [h for h in recording_app.handlers if isinstance(h, CommandHandler)]
    assert len(message_handlers) >= 1
    assert len(command_handlers) >= 1

    message_handler = message_handlers[0]
    assert message_handler.filters.check_update(_make_update("/sessions", is_command=True)) is False
    assert message_handler.filters.check_update(_make_update("olá", is_command=False)) is True

    command_handler = command_handlers[0]
    assert command_handler.commands == frozenset({"new", "title", "resume", "sessions"})


def test_message_handler_filter_rejects_slash_command_accepts_plain_text() -> None:
    """REQ-010 cenário "Slash command não aciona o MessageHandler".

    O filtro `filters.TEXT & ~filters.COMMAND` usado pelo gateway rejeita
    `/sessions` (para o `CommandHandler` cuidar) e aceita uma mensagem
    normal como "olá".
    """
    handler = MessageHandler(filters.TEXT & ~filters.COMMAND, callback=lambda u, c: None)

    assert handler.check_update(_make_update("/sessions", is_command=True)) is False
    assert handler.check_update(_make_update("olá", is_command=False)) is True


def test_command_handler_rejects_plain_text_message() -> None:
    """REQ-010 cenário "Mensagem normal não aciona o CommandHandler".

    O `CommandHandler` com os comandos do gateway rejeita uma mensagem
    normal ("olá") — quem a atende é o `MessageHandler`.
    """
    handler = CommandHandler(
        ["new", "title", "resume", "sessions"], callback=lambda u, c: None
    )

    result = handler.check_update(_make_update("olá", is_command=False))
    assert not result


def test_main_registers_callback_query_handler_after_message_and_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit 'telegram_gateway.main() registers a CallbackQueryHandler in addition to
    MessageHandler and CommandHandler' (task `telegram-tool-approval-task-gateway-5`).

    Given a `main()` run with valid env vars and a fake `Application` whose
    `add_handler` records each call, `main()` MUST call `add_handler`
    exactly 4 times: one for `MessageHandler` (filters.TEXT & ~filters.COMMAND,
    the existing message handler), one for `CommandHandler` (existing
    /new /title /resume /sessions), one for the `/start` `CommandHandler`
    (`channel-link-wiring`, account linking), and one for `CallbackQueryHandler`
    (produced by `approval.make_approval_callback_handler`).

    The CallbackQueryHandler MUST be the LAST one registered
    (handler-order invariant — the same order used by `python-telegram-bot`
    examples for slash commands + free text + buttons).
    """
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_AUTHORIZED_CHAT_ID", "123")
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    monkeypatch.setattr(telegram_schema, "ensure_telegram_threads_schema", lambda uri: None)
    monkeypatch.setattr(usage_schema, "ensure_schema", lambda uri: None)
    monkeypatch.setattr(
        "src.infrastructure.agent_runtime.checkpoint_schema.ensure_langgraph_checkpoint_schema",
        lambda uri: None,
    )
    monkeypatch.setattr(
        "src.infrastructure.persistence.telegram_link_codes_schema.ensure_schema",
        lambda uri: None,
    )
    monkeypatch.setattr(
        "src.infrastructure.persistence.user_integrations_schema.ensure_schema",
        lambda uri: None,
    )
    monkeypatch.setattr(telegram_gateway, "build_runner", lambda *, postgres_uri: object())

    # Substitui a fábrica por uma versão controlada ANTES de chamar main(),
    # se ela existir. Se a fábrica não existir (RED), o teste vai falhar
    # na próxima assertion (`len(handlers) == 3`), que é a falha certa.
    factory_called_with: dict[str, Any] = {}

    def _factory(*, authorized_chat_id: str, agent_runner: Any, bot: Any) -> Any:
        factory_called_with["authorized_chat_id"] = authorized_chat_id
        factory_called_with["agent_runner"] = agent_runner
        factory_called_with["bot"] = bot

        async def _noop(update: Any, context: Any) -> None:
            return None

        return CallbackQueryHandler(_noop)

    if hasattr(telegram_approval, "make_approval_callback_handler"):
        monkeypatch.setattr(
            telegram_approval, "make_approval_callback_handler", _factory
        )

    recording_app = _RecordingApplication()
    monkeypatch.setattr(telegram_gateway, "build_application", lambda _cfg: recording_app)

    exit_code = telegram_gateway.main()

    assert exit_code == 0
    assert recording_app.run_polling_called is True
    assert len(recording_app.handlers) == 4, (
        f"main() deve registrar exatamente 4 handlers "
        f"(MessageHandler, CommandHandler, CommandHandler[start], CallbackQueryHandler), "
        f"registrou {len(recording_app.handlers)}: {recording_app.handlers!r}"
    )

    # Tipos esperados.
    assert isinstance(recording_app.handlers[0], MessageHandler)
    assert isinstance(recording_app.handlers[1], CommandHandler)
    assert isinstance(recording_app.handlers[2], CommandHandler)
    assert "start" in recording_app.handlers[2].commands
    # O CallbackQueryHandler é o ÚLTIMO registrado.
    assert isinstance(recording_app.handlers[3], CallbackQueryHandler), (
        "CallbackQueryHandler deve ser registrado por ÚLTIMO "
        "(após MessageHandler e os dois CommandHandler)."
    )

    # A fábrica foi invocada com os args corretos.
    assert factory_called_with["authorized_chat_id"] == "123"
    assert factory_called_with["agent_runner"] is not None
    assert factory_called_with["bot"] is recording_app.bot


def test_main_calls_checkpoint_schema_ensure_before_run_polling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-ADD-001: ensure checkpoint schema before polling; fail-fast on error.

    WHEN telegram_gateway bootstrap completes successfully
    THEN `ensure_langgraph_checkpoint_schema` was invoked before `run_polling`
    AND if ensure raises, the polling loop does not start.
    """
    call_order: list[str] = []

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_AUTHORIZED_CHAT_ID", "123")
    monkeypatch.setenv("POSTGRES_URI", "postgresql://checkpoint-bootstrap")

    monkeypatch.setattr(
        telegram_schema, "ensure_telegram_threads_schema", lambda uri: None
    )
    monkeypatch.setattr(usage_schema, "ensure_schema", lambda uri: None)
    monkeypatch.setattr(
        "src.infrastructure.agent_runtime.checkpoint_schema.ensure_langgraph_checkpoint_schema",
        lambda uri: call_order.append(f"ensure:{uri}"),
    )
    monkeypatch.setattr(
        "src.infrastructure.persistence.telegram_link_codes_schema.ensure_schema",
        lambda uri: None,
    )
    monkeypatch.setattr(
        "src.infrastructure.persistence.user_integrations_schema.ensure_schema",
        lambda uri: None,
    )
    monkeypatch.setattr(
        telegram_gateway, "build_runner", lambda *, postgres_uri: object()
    )

    recording_app = _RecordingApplication()
    monkeypatch.setattr(
        telegram_gateway, "build_application", lambda _cfg: recording_app
    )

    def _run_polling(*_a: Any, **_k: Any) -> None:
        call_order.append("run_polling")
        recording_app.run_polling_called = True

    monkeypatch.setattr(recording_app, "run_polling", _run_polling)

    exit_code = telegram_gateway.main()

    assert exit_code == 0
    assert "ensure:postgresql://checkpoint-bootstrap" in call_order
    assert "run_polling" in call_order
    assert call_order.index("ensure:postgresql://checkpoint-bootstrap") < call_order.index(
        "run_polling"
    )

    # Fail-fast: ensure raises → polling MUST NOT start.
    call_order.clear()
    recording_app.run_polling_called = False

    def _ensure_fails(uri: str) -> None:
        call_order.append(f"ensure:{uri}")
        raise RuntimeError("postgres unreachable")

    monkeypatch.setattr(
        "src.infrastructure.agent_runtime.checkpoint_schema.ensure_langgraph_checkpoint_schema",
        _ensure_fails,
    )

    with pytest.raises(RuntimeError, match="postgres unreachable"):
        telegram_gateway.main()

    assert recording_app.run_polling_called is False
    assert "run_polling" not in call_order


def test_main_registers_start_command_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit 'gateway registers /start handler' (channel-link-wiring-task-gateway-1
    unit-1 / telegram-start-command-wiring REQ-001).

    main() MUST register a CommandHandler covering "start", wired to
    make_start_command_handler backed by a RedeemTelegramLinkCode instance.
    """
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_AUTHORIZED_CHAT_ID", "123")
    monkeypatch.setenv("POSTGRES_URI", "postgresql://fake")
    monkeypatch.setattr(telegram_schema, "ensure_telegram_threads_schema", lambda uri: None)
    monkeypatch.setattr(usage_schema, "ensure_schema", lambda uri: None)
    monkeypatch.setattr(
        "src.infrastructure.agent_runtime.checkpoint_schema.ensure_langgraph_checkpoint_schema",
        lambda uri: None,
    )
    monkeypatch.setattr(
        "src.infrastructure.persistence.telegram_link_codes_schema.ensure_schema",
        lambda uri: None,
    )
    monkeypatch.setattr(
        "src.infrastructure.persistence.user_integrations_schema.ensure_schema",
        lambda uri: None,
    )
    monkeypatch.setattr(telegram_gateway, "build_runner", lambda *, postgres_uri: object())

    factory_called_with: dict[str, Any] = {}

    def _fake_start_factory(*, redeem_use_case: Any, bot: Any) -> Any:
        factory_called_with["redeem_use_case"] = redeem_use_case
        factory_called_with["bot"] = bot

        async def _noop(update: Any, context: Any) -> None:
            return None

        return _noop

    monkeypatch.setattr(
        telegram_start_command, "make_start_command_handler", _fake_start_factory
    )

    recording_app = _RecordingApplication()
    monkeypatch.setattr(telegram_gateway, "build_application", lambda _cfg: recording_app)

    exit_code = telegram_gateway.main()

    assert exit_code == 0
    command_handlers = [h for h in recording_app.handlers if isinstance(h, CommandHandler)]
    start_handlers = [h for h in command_handlers if "start" in h.commands]
    assert len(start_handlers) == 1, (
        "expected exactly one CommandHandler covering 'start', found command "
        f"handlers: {[getattr(h, 'commands', None) for h in command_handlers]}"
    )
    assert isinstance(factory_called_with.get("redeem_use_case"), RedeemTelegramLinkCode)
    assert factory_called_with.get("bot") is recording_app.bot


def test_main_ensures_telegram_link_codes_and_user_integrations_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit 'gateway ensures telegram_link_codes/user_integrations schema'
    (channel-link-wiring-task-gateway-1 unit-2 / telegram-start-command-wiring REQ-001).

    Both schema-ensure calls MUST happen before run_polling(), mirroring the
    gateway's existing fail-fast pattern for its other three schemas.
    """
    call_order: list[str] = []

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_AUTHORIZED_CHAT_ID", "123")
    monkeypatch.setenv("POSTGRES_URI", "postgresql://schema-test")
    monkeypatch.setattr(telegram_schema, "ensure_telegram_threads_schema", lambda uri: None)
    monkeypatch.setattr(usage_schema, "ensure_schema", lambda uri: None)
    monkeypatch.setattr(
        "src.infrastructure.agent_runtime.checkpoint_schema.ensure_langgraph_checkpoint_schema",
        lambda uri: None,
    )
    monkeypatch.setattr(
        "src.infrastructure.persistence.telegram_link_codes_schema.ensure_schema",
        lambda uri: call_order.append(f"telegram_link_codes:{uri}"),
    )
    monkeypatch.setattr(
        "src.infrastructure.persistence.user_integrations_schema.ensure_schema",
        lambda uri: call_order.append(f"user_integrations:{uri}"),
    )
    monkeypatch.setattr(telegram_gateway, "build_runner", lambda *, postgres_uri: object())

    recording_app = _RecordingApplication()
    monkeypatch.setattr(telegram_gateway, "build_application", lambda _cfg: recording_app)

    def _run_polling(*_a: Any, **_k: Any) -> None:
        call_order.append("run_polling")
        recording_app.run_polling_called = True

    monkeypatch.setattr(recording_app, "run_polling", _run_polling)

    exit_code = telegram_gateway.main()

    assert exit_code == 0
    assert "telegram_link_codes:postgresql://schema-test" in call_order
    assert "user_integrations:postgresql://schema-test" in call_order
    assert call_order.index("telegram_link_codes:postgresql://schema-test") < call_order.index(
        "run_polling"
    )
    assert call_order.index("user_integrations:postgresql://schema-test") < call_order.index(
        "run_polling"
    )
