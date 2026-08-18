"""Adapter Postgres de `AgentProfileRepositoryPort`.

Todas as queries filtram por `user_id` (mesmo padrão de
`PostgresEmailAccountRepository` e `PostgresCrmRepository`). Miss
cross-user → `None` (nunca exceção). Conexão por operação (psycopg async).
"""
from __future__ import annotations

import json
from typing import Any

import psycopg

from src.application.ports.agent_profile_repository import (
    AgentProfileRepositoryPort,
)
from src.domain.agents import AgentProfile, DuplicateAgentProfileError
from src.domain.shared.errors import DomainError

_COLUMNS = (
    "id, user_id, name, slug, system_prompt, skills_allowlist, "
    "tools_allowlist, tier, model_override, is_active, archived_at, "
    "created_at, updated_at"
)


def _decode_jsonb(value: Any) -> list[str] | None:
    """Decodifica JSONB (psycopg devolve str/bytes/dict/list conforme config)."""
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        data = value
    elif isinstance(value, (str, bytes, bytearray)):
        data = json.loads(value)
    else:
        raise DomainError(f"Tipo inesperado em JSONB: {type(value).__name__}")
    if not isinstance(data, list):
        raise DomainError("skills_allowlist/tools_allowlist deve ser lista.")
    return [str(item) for item in data]


def _row_to_profile(row: tuple[Any, ...]) -> AgentProfile:
    """Reconstrói um `AgentProfile` a partir de uma linha do `agent_profiles`."""
    (
        profile_id,
        user_id,
        name,
        slug,
        system_prompt,
        skills_allowlist,
        tools_allowlist,
        tier,
        model_override,
        is_active,
        archived_at,
        created_at,
        updated_at,
    ) = row
    return AgentProfile(
        id=str(profile_id),
        user_id=str(user_id),
        name=name,
        slug=slug,
        system_prompt=system_prompt,
        skills_allowlist=_decode_jsonb(skills_allowlist),
        tools_allowlist=_decode_jsonb(tools_allowlist),
        tier=int(tier),
        model_override=model_override,
        is_active=bool(is_active),
        archived_at=archived_at,
        created_at=created_at,
        updated_at=updated_at,
    )


class PostgresAgentProfileRepository(AgentProfileRepositoryPort):
    """Persiste `AgentProfile` na tabela `agent_profiles`, escopada a `user_id`."""

    def __init__(self, conninfo: str) -> None:
        """Guarda o conninfo Postgres — uma conexão é aberta por operação."""
        self._conninfo = conninfo

    async def create(self, profile: AgentProfile) -> AgentProfile:
        """Insere o perfil e devolve a linha persistida."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        f"""
                        INSERT INTO agent_profiles ({_COLUMNS})
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING {_COLUMNS}
                        """,
                        (
                            profile.id,
                            profile.user_id,
                            profile.name,
                            profile.slug,
                            profile.system_prompt,
                            json.dumps(profile.skills_allowlist)
                            if profile.skills_allowlist is not None
                            else None,
                            json.dumps(profile.tools_allowlist)
                            if profile.tools_allowlist is not None
                            else None,
                            profile.tier,
                            profile.model_override,
                            profile.is_active,
                            profile.archived_at,
                            profile.created_at,
                            profile.updated_at,
                        ),
                    )
                    row = await cur.fetchone()
                await conn.commit()
            except psycopg.errors.UniqueViolation as exc:
                await conn.rollback()
                raise DuplicateAgentProfileError(
                    f"Já existe um agent_profile ativo com slug '{profile.slug}' "
                    f"para este user_id."
                ) from exc
        assert row is not None
        return _row_to_profile(row)

    async def get(self, user_id: str, profile_id: str) -> AgentProfile | None:
        """Retorna o perfil do `user_id` ou `None` (miss ou cross-user)."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_COLUMNS} FROM agent_profiles "
                    f"WHERE user_id = %s AND id = %s",
                    (user_id, profile_id),
                )
                row = await cur.fetchone()
        return _row_to_profile(row) if row else None

    async def get_by_slug(
        self, user_id: str, slug: str
    ) -> AgentProfile | None:
        """Retorna o perfil ativo (não arquivado) do `user_id` pelo slug."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_COLUMNS} FROM agent_profiles "
                    f"WHERE user_id = %s AND slug = %s "
                    f"AND archived_at IS NULL",
                    (user_id, slug),
                )
                row = await cur.fetchone()
        return _row_to_profile(row) if row else None

    async def get_default(self, user_id: str) -> AgentProfile | None:
        """Retorna o perfil default (mais antigo ativo) ou `None` se vazio."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_COLUMNS} FROM agent_profiles "
                    f"WHERE user_id = %s AND is_active = TRUE "
                    f"ORDER BY created_at ASC LIMIT 1",
                    (user_id,),
                )
                row = await cur.fetchone()
        return _row_to_profile(row) if row else None

    async def list_by_user(
        self, user_id: str, *, include_archived: bool = False
    ) -> list[AgentProfile]:
        """Retorna os perfis do `user_id`, ordenados por criação ASC."""
        where_extra = "" if include_archived else "AND archived_at IS NULL"
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_COLUMNS} FROM agent_profiles "
                    f"WHERE user_id = %s {where_extra} "
                    f"ORDER BY created_at ASC",
                    (user_id,),
                )
                rows = await cur.fetchall()
        return [_row_to_profile(r) for r in rows]

    async def update(self, profile: AgentProfile) -> AgentProfile | None:
        """Atualiza o perfil próprio; `None` se miss ou cross-user."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    UPDATE agent_profiles SET
                        name = %s, system_prompt = %s,
                        skills_allowlist = %s, tools_allowlist = %s,
                        tier = %s, model_override = %s,
                        is_active = %s, archived_at = %s,
                        updated_at = %s
                    WHERE user_id = %s AND id = %s
                    RETURNING {_COLUMNS}
                    """,
                    (
                        profile.name,
                        profile.system_prompt,
                        json.dumps(profile.skills_allowlist)
                        if profile.skills_allowlist is not None
                        else None,
                        json.dumps(profile.tools_allowlist)
                        if profile.tools_allowlist is not None
                        else None,
                        profile.tier,
                        profile.model_override,
                        profile.is_active,
                        profile.archived_at,
                        profile.updated_at,
                        profile.user_id,
                        profile.id,
                    ),
                )
                row = await cur.fetchone()
            await conn.commit()
        return _row_to_profile(row) if row else None

    async def archive(
        self, user_id: str, profile_id: str
    ) -> AgentProfile | None:
        """Soft-delete: set `is_active=False`, `archived_at=now`; idempotente."""
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    UPDATE agent_profiles SET
                        is_active = FALSE,
                        archived_at = NOW(),
                        updated_at = NOW()
                    WHERE user_id = %s AND id = %s
                    RETURNING {_COLUMNS}
                    """,
                    (user_id, profile_id),
                )
                row = await cur.fetchone()
            await conn.commit()
        return _row_to_profile(row) if row else None
