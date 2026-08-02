"""Auto-migração do vínculo Telegram legado (design Migration Plan passo 2).

Na primeira subida do `telegram_gateway` após o deploy desta mudança, se
`TELEGRAM_AUTHORIZED_CHAT_ID` está configurado e `user_integrations` ainda
não tem NENHUMA linha `integration_type="telegram"` (de nenhum usuário),
cria automaticamente um vínculo para o admin mais antigo
(`role='admin'`, menor `created_at`) — preserva o setup do único admin já
configurado sem exigir nenhuma ação manual (REQ-002 do delta
`telegram-channel`, task `user-integration-credentials-task-migration-1`).

Roda sync, ANTES do `application.run_polling()` iniciar, no mesmo estilo de
`auth.schema.bootstrap_admin` (checa "já existe algo?" antes de inserir).
Assume que o schema de `user_integrations`/`users` já foi garantido pelo
chamador (mesmo contrato de `bootstrap_admin` em relação a `ensure_schema`).
"""
from __future__ import annotations

import asyncio
import logging
import uuid

import psycopg

from src.domain.integrations import UserIntegration
from src.infrastructure.persistence.user_integrations_repository import (
    PostgresUserIntegrationRepository,
)

logger = logging.getLogger(__name__)

_TELEGRAM_INTEGRATION_TYPE = "telegram"

_HAS_TELEGRAM_ROW = (
    "SELECT 1 FROM user_integrations WHERE integration_type = %s LIMIT 1"
)
_EARLIEST_ADMIN = (
    "SELECT id FROM users WHERE role = 'admin' ORDER BY created_at ASC LIMIT 1"
)


def auto_migrate_legacy_chat_binding(
    *, postgres_uri: str, authorized_chat_id: str
) -> None:
    """Cria o vínculo `chat_id → admin mais antigo` na primeira subida pós-deploy.

    No-op se JÁ existe qualquer linha `telegram` em `user_integrations` (de
    qualquer usuário) — nunca sobrescreve um vínculo real, seja de uma
    instância multi-admin já provisionada, seja de uma já migrada
    anteriormente. Também no-op (com log de aviso) se não houver nenhum
    usuário `role='admin'` para vincular — não deveria acontecer em
    condições normais (`bootstrap_admin` garante o primeiro admin), mas não
    é motivo para derrubar o startup do gateway.
    """
    with psycopg.connect(postgres_uri) as conn:
        with conn.cursor() as cur:
            cur.execute(_HAS_TELEGRAM_ROW, (_TELEGRAM_INTEGRATION_TYPE,))
            if cur.fetchone() is not None:
                return
            cur.execute(_EARLIEST_ADMIN)
            row = cur.fetchone()

    if row is None:
        logger.warning(
            "Auto-migração do vínculo Telegram legado pulada: nenhum "
            "usuário role='admin' encontrado."
        )
        return

    admin_id = str(row[0])
    integration = UserIntegration(
        id=str(uuid.uuid4()),
        user_id=admin_id,
        integration_type=_TELEGRAM_INTEGRATION_TYPE,
        config={"chat_id": authorized_chat_id},
    )
    repository = PostgresUserIntegrationRepository(postgres_uri)
    asyncio.run(repository.save(integration))
    logger.info(
        "Auto-migração: vínculo Telegram legado chat_id=%s criado para "
        "user_id=%s (admin mais antigo).",
        authorized_chat_id,
        admin_id,
    )
