"""Adapter Postgres de `UserIntegrationRepositoryPort` (task
`user-integration-credentials-task-store-2`).

Cifra/decifra os valores de `config` (REQ-002 do spec
`user-integration-credentials-store`) usando o helper de
`credentials_crypto.py`, e persiste como JSONB — o envelope usado aqui é um
dict `{ "__enc__": "<ciphertext>" }` por valor sensível, o que mantém a
coluna como JSONB válido (sem `CHECK` que restrinja formato — ver
`user_integrations_schema.py`).

Padrão de acesso a banco: `psycopg` assíncrono, uma conexão por operação,
mesmo de `scheduled_task_repository.py` — funciona tanto no servidor
quanto no `jeff_cli` subprocess.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import psycopg

from src.application.ports.user_integration_repository import (
    UserIntegrationRepositoryPort,
)
from src.domain.integrations import UserIntegration
from src.infrastructure.persistence.credentials_crypto import decrypt, encrypt

logger = logging.getLogger(__name__)

_COLUMNS = "id, user_id, integration_type, config, created_at, updated_at"

_UPSERT = f"""
INSERT INTO user_integrations ({_COLUMNS})
VALUES (%s, %s, %s, %s::jsonb, %s, %s)
ON CONFLICT (id) DO UPDATE SET
    user_id = EXCLUDED.user_id,
    integration_type = EXCLUDED.integration_type,
    config = EXCLUDED.config,
    updated_at = EXCLUDED.updated_at
"""

_SELECT_BY_ID = f"SELECT {_COLUMNS} FROM user_integrations WHERE id = %s"
_SELECT_BY_USER = (
    f"SELECT {_COLUMNS} FROM user_integrations WHERE user_id = %s ORDER BY created_at"
)
_SELECT_ALL = f"SELECT {_COLUMNS} FROM user_integrations ORDER BY created_at"
_DELETE = "DELETE FROM user_integrations WHERE id = %s"

_ENVELOPE_KEY = "__enc__"


def _encrypt_config(config: dict[str, object]) -> dict[str, object]:
    """Cifra cada valor de `config`, embrulhando em `{__enc__: ct}`.

    SEMPRE serializa o valor via `json.dumps` antes de cifrar — inclusive
    strings — para que `_decrypt_config` possa desfazer com `json.loads` sem
    ambiguidade. Bug real encontrado em produção (2026-08-03): a versão
    anterior só serializava valores NÃO-string, deixando strings puramente
    numéricas (`chat_id`/`phone_number`, ex. "556199976245") indistinguíveis
    de um número JSON — `json.loads("556199976245")` devolve o `int`
    556199976245, quebrando toda comparação `== phone_number` downstream em
    `resolve_whatsapp_user_id`/`resolve_telegram_user_id`. Serializar SEMPRE
    (`json.dumps("556199976245")` → `'"556199976245"'`) remove a ambiguidade:
    o tipo original é sempre recuperável.
    """
    encrypted: dict[str, object] = {}
    for key, value in config.items():
        encrypted[key] = {_ENVELOPE_KEY: encrypt(json.dumps(value))}
    return encrypted


def _decrypt_config(config: dict[str, object]) -> dict[str, object]:
    """Inverso de `_encrypt_config`: decifra cada valor encriptado.

    Valores que NÃO estão no envelope são passados adiante como estão
    (defensivo: protege contra dados legados não-encriptados ou chaves
    diferentes misturadas na mesma linha). Linhas cifradas pela versão
    anterior (string crua, sem `json.dumps`) continuam parseáveis pelo
    fallback abaixo, mas para valores puramente numéricos ainda voltam como
    `int` — dados legados precisam ser regravados (basta salvar de novo)
    para se beneficiar do formato sem ambiguidade.
    """
    decrypted: dict[str, object] = {}
    for key, value in config.items():
        if isinstance(value, dict) and _ENVELOPE_KEY in value:
            ciphertext = value[_ENVELOPE_KEY]
            if not isinstance(ciphertext, str):
                # Formato inesperado — passa adiante em vez de quebrar o get.
                decrypted[key] = value
                continue
            plaintext = decrypt(ciphertext)
            try:
                decrypted[key] = json.loads(plaintext)
            except (TypeError, ValueError):
                # Formato legado que não era JSON válido — era string crua mesmo.
                decrypted[key] = plaintext
        else:
            decrypted[key] = value
    return decrypted


def _row_to_integration(row: tuple[Any, ...]) -> UserIntegration:
    integration_id, user_id, integration_type, config, created_at, updated_at = row
    return UserIntegration(
        id=str(integration_id),
        user_id=str(user_id),
        integration_type=integration_type,
        config=_decrypt_config(config),
        created_at=created_at,
        updated_at=updated_at,
    )


def _rows_to_integrations_skipping_undecryptable(
    rows: list[tuple[Any, ...]],
) -> list[UserIntegration]:
    """Decifra cada linha; uma linha com ciphertext que não bate com a chave
    ATIVA (`INTEGRATION_CREDENTIALS_KEY` rotacionada/perdida, dado órfão) é
    logada e pulada, em vez de derrubar a leitura de todas as outras linhas.

    Achado em produção (2026-08-03): `resolve_whatsapp_user_id`/
    `resolve_telegram_user_id` varrem TODAS as linhas num loop de busca — uma
    única linha corrompida em qualquer canto da tabela travava a resolução de
    QUALQUER usuário, incluindo vínculos recém-criados e válidos.
    """
    integrations: list[UserIntegration] = []
    for row in rows:
        try:
            integrations.append(_row_to_integration(row))
        except ValueError:
            integration_id = row[0]
            logger.warning(
                "user_integrations id=%s não pôde ser decifrada com a chave "
                "ativa — pulada (não derruba as demais linhas).",
                integration_id,
            )
    return integrations


class PostgresUserIntegrationRepository(UserIntegrationRepositoryPort):
    """Persiste `UserIntegration` na tabela `user_integrations` com cifra em `config`."""

    def __init__(self, conninfo: str) -> None:
        """Guarda o conninfo Postgres — uma conexão é aberta por operação."""
        self._conninfo = conninfo

    async def save(self, integration: UserIntegration) -> None:
        """Upsert por `id`: cifra `config` e persiste (REQ-001/REQ-002)."""
        encrypted_config = _encrypt_config(integration.config)
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    _UPSERT,
                    (
                        integration.id,
                        integration.user_id,
                        integration.integration_type,
                        json.dumps(encrypted_config),
                        integration.created_at,
                        integration.updated_at,
                    ),
                )
            await conn.commit()

    async def get(self, integration_id: str) -> UserIntegration | None:
        """Retorna a entrada decifrada ou `None` (nunca exceção) para id inexistente."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(_SELECT_BY_ID, (integration_id,))
                row = await cur.fetchone()
        return _row_to_integration(row) if row is not None else None

    async def list_by_user(self, user_id: str) -> list[UserIntegration]:
        """Retorna as entradas do `user_id`, decifradas (REQ-001).

        Uma linha undecryptável com a chave ativa é pulada (logada), em vez
        de derrubar a listagem inteira do usuário.
        """
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(_SELECT_BY_USER, (user_id,))
                rows = await cur.fetchall()
        return _rows_to_integrations_skipping_undecryptable(rows)

    async def list_all(self) -> list[UserIntegration]:
        """Retorna TODAS as entradas, decifradas, de todos os usuários (REQ-004).

        A checagem `role=admin` é responsabilidade do use case chamador. Uma
        linha undecryptável com a chave ativa é pulada (logada) — ver
        `_rows_to_integrations_skipping_undecryptable`.
        """
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(_SELECT_ALL)
                rows = await cur.fetchall()
        return _rows_to_integrations_skipping_undecryptable(rows)

    async def delete(self, integration_id: str) -> None:
        """Remove a entrada; tolerante a `integration_id` inexistente (no-op)."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(_DELETE, (integration_id,))
            await conn.commit()
