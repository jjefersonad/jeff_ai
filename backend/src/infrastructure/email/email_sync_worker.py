"""Gateway do `email_sync_worker` (processo próprio de longa duração).

Responsabilidades:

- Carregar `POSTGRES_URI` (obrigatório) e `EMAIL_SYNC_POLL_INTERVAL_SECONDS`
  (opcional, default conservador) do ambiente.
- Falhar rápido (com mensagem citando as env vars faltantes) se `POSTGRES_URI`
  não estiver setada — sem Postgres não há como varrer contas nem persistir
  mensagens.
- Garantir o schema das tabelas `email_accounts`/`emails`/
  `email_attachments` (`ensure_email_schema`) antes de iniciar o polling.
  Idempotente, mesmo padrão de `crm_schema`/`user_integrations_schema`.
- Construir o `EmailSyncWorker` com as portas Postgres e o fetch client real
  (`fetch_new_messages` de `src/infrastructure/email/imap_client.py`).
- Iniciar um loop infinito de `worker.poll_once()` seguido de `asyncio.sleep`
  pelo intervalo configurado. Cancelamento limpo via `KeyboardInterrupt`
  / `asyncio.CancelledError`.

Modelo em `src/infrastructure/telegram/telegram_gateway.py` (design
Decision 2 de `email-client-imap-mvp`): um container dedicado de vida longa,
independente do processo da API HTTP.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

from src.composition.env import load_env
from src.infrastructure.email.imap_client import fetch_new_messages
from src.infrastructure.email.sync_worker import EmailSyncWorker
from src.infrastructure.persistence.crm_repository import PostgresCrmRepository
from src.infrastructure.persistence.email_account_repository import (
    PostgresEmailAccountRepository,
)
from src.infrastructure.persistence.email_repository import PostgresEmailRepository
from src.infrastructure.persistence.email_schema import ensure_email_schema
from src.infrastructure.persistence.user_integrations_repository import (
    PostgresUserIntegrationRepository,
)

logger = logging.getLogger(__name__)


class EmailSyncWorkerConfigError(RuntimeError):
    """Levantada quando o `bootstrap_config` encontra configuração inválida."""


# Default conservador: 60s entre passadas. Bem dentro do orçamento para
# provedores IMAP típicos sem rate-limit agressivo, e mantém latência de
# inbox baixa para usuários novos. Operador pode ajustar via env var.
DEFAULT_POLL_INTERVAL_SECONDS = 60


def _collect_missing_envs(names: tuple[str, ...]) -> list[str]:
    """Devolve a lista de `names` cujo valor de ambiente está ausente ou vazio.

    Strings vazias são tratadas como ausentes — env var declarada sem valor
    não é config válida (mesmo padrão do `telegram_gateway`).
    """
    return [name for name in names if not os.environ.get(name)]


def bootstrap_config() -> tuple[str, int]:
    """Lê e valida as env vars do worker. Falha rápido se faltar `POSTGRES_URI`.

    Returns:
        Tupla `(postgres_uri, poll_interval_seconds)`. `poll_interval_seconds`
        é derivado de `EMAIL_SYNC_POLL_INTERVAL_SECONDS` quando setada e
        parseável como inteiro positivo; senão `DEFAULT_POLL_INTERVAL_SECONDS`.

    Raises:
        EmailSyncWorkerConfigError: `POSTGRES_URI` ausente/vazia.
    """
    missing = _collect_missing_envs(("POSTGRES_URI",))
    if missing:
        env_list = ", ".join(missing)
        raise EmailSyncWorkerConfigError(
            f"Configuração do email_sync_worker incompleta — faltando: {env_list}. "
            "Defina-as em ./.env antes de iniciar o email_sync_worker."
        )

    raw_interval = os.environ.get("EMAIL_SYNC_POLL_INTERVAL_SECONDS", "")
    if raw_interval:
        try:
            interval = int(raw_interval)
            if interval <= 0:
                raise ValueError("intervalo deve ser positivo")
        except ValueError as exc:
            raise EmailSyncWorkerConfigError(
                f"EMAIL_SYNC_POLL_INTERVAL_SECONDS inválida: {raw_interval!r} "
                f"({exc}). Use um inteiro positivo em segundos."
            ) from exc
    else:
        interval = DEFAULT_POLL_INTERVAL_SECONDS

    return os.environ["POSTGRES_URI"], interval


async def _run_loop(worker: EmailSyncWorker, interval_seconds: int) -> None:
    """Loop infinito: `poll_once()` + `asyncio.sleep(interval_seconds)`.

    Cancelamento cooperativo via `asyncio.CancelledError` (SIGTERM do
    `docker compose stop` cai aqui) — sai sem traceback.
    """
    while True:
        try:
            await worker.poll_once()
        except Exception:
            # Falha não-trip-wire o loop: loga e tenta a próxima iteração.
            # O `EmailSyncWorker._poll_account` já marca `status=error` por
            # conta e continua; exceções aqui vêm de algo mais estrutural
            # (perda de conexão com Postgres, etc.) — não vale derrubar o
            # worker, vale tentar de novo no próximo tick.
            logger.exception("[email_sync_worker] poll_once falhou; retrying")
        await asyncio.sleep(interval_seconds)


async def main() -> int:
    """Entry point async: monta config, garante schema, inicia o loop.

    Returns:
        Exit code (`0` em shutdown limpo, `2` em configuração inválida).
    """
    load_env()
    try:
        conninfo, interval_seconds = bootstrap_config()
    except EmailSyncWorkerConfigError as exc:
        # Mensagem clara no stderr; o operador corrige uma única env var.
        logger.error("[email_sync_worker] %s", exc)
        return 2

    ensure_email_schema(conninfo)
    logger.info("[email_sync_worker] schema garantido; iniciando loop")

    worker = EmailSyncWorker(
        account_repository=PostgresEmailAccountRepository(conninfo),
        integration_repository=PostgresUserIntegrationRepository(conninfo),
        email_repository=PostgresEmailRepository(conninfo),
        crm_repository=PostgresCrmRepository(conninfo),
        fetch_messages=fetch_new_messages,
    )

    # Cancela cooperativamente em SIGTERM/SIGINT (compose down envia SIGTERM).
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _request_stop(*_: object) -> None:
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _request_stop)

    worker_task = asyncio.create_task(_run_loop(worker, interval_seconds))
    stop_task = asyncio.create_task(stop_event.wait())
    done, pending = await asyncio.wait(
        {worker_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
    for task in pending:
        try:
            await task
        except asyncio.CancelledError:
            pass
    logger.info("[email_sync_worker] shutdown solicitado — saindo")
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    sys.exit(asyncio.run(main()))
