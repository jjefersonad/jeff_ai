"""Router HTTP para CRUD de `AgentProfile` (spec `agent-profile-crud`).

Todas as rotas exigem autenticação: `require_auth` está registrada como
dependency global no `FastAPI(...)` de `webapp.py`, então este router não a
redeclara por endpoint (mesmo padrão dos routers já em produção).
`user_id` vem sempre do `User` resolvido por `require_auth` (`user.id`),
nunca do body — mesma política de CRM/Email/Scheduling.

`DuplicateAgentProfileError` é mapeada para 409 (conflito de chave natural
`(user_id, slug)`); `DomainError` para 422 (validação/invariante);
miss/cross-user em GET/PATCH/POST archive vira 404 (mesma defesa de não
revelar existência usada em CRM/Email). `DELETE` não é suportado por
design — soft-delete via `POST /{id}/archive` (REQ-005).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from src.application.use_cases.archive_agent_profile import ArchiveAgentProfile
from src.application.use_cases.create_agent_profile import CreateAgentProfile
from src.application.use_cases.get_agent_profile import GetAgentProfile
from src.application.use_cases.list_agent_profiles import ListAgentProfiles
from src.application.use_cases.update_agent_profile import (
    UNSET,
    UpdateAgentProfile,
)
from src.composition.dependencies import (
    _archive_agent_profile_use_case,
    _create_agent_profile_use_case,
    _get_agent_profile_use_case,
    _list_agent_profiles_use_case,
    _update_agent_profile_use_case,
)
from src.domain.agents import AgentProfile, DuplicateAgentProfileError
from src.domain.shared.errors import DomainError
from src.infrastructure.auth.dependencies import require_auth
from src.infrastructure.auth.users import User

# ---------- Schemas ---------- #


class AgentProfileOut(BaseModel):
    """Representação HTTP de um `AgentProfile`.

    Espelha os campos da entidade de domínio, mas com datas como `str`
    ISO-8601 (não `datetime` cru) para eliminar ambiguidade de timezone
    no JSON. `ConfigDict(from_attributes=True)` está aqui como defesa:
    o conversor `_profile_to_out` hoje materializa campo a campo, mas
    simplificações futuras que voltem a passar a entidade direto
    continuam funcionando.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    slug: str
    system_prompt: str
    skills_allowlist: list[str] | None
    tools_allowlist: list[str] | None
    mcp_allowlist: list[str] | None
    tier: int
    model_override: str | None
    is_active: bool
    archived_at: str | None
    created_at: str
    updated_at: str


class AgentProfileCreateIn(BaseModel):
    """Payload de criação (REQ-001).

    `slug` validado só em comprimento pelo Pydantic; a regra de
    kebab-case canônico vive no domínio (`AgentProfile.validate_slug_format`)
    e levanta `DomainError` no use case, chegando ao HTTP como 422.
    """

    name: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=100)
    system_prompt: str = Field(..., min_length=1)
    skills_allowlist: list[str] | None = None
    tools_allowlist: list[str] | None = None
    mcp_allowlist: list[str] | None = None
    tier: int = Field(1, ge=1, le=4)
    model_override: str | None = None


class AgentProfileUpdateIn(BaseModel):
    """Payload de atualização parcial (REQ-004).

    Todos os campos opcionais. `None` em `skills_allowlist`/
    `tools_allowlist`/`mcp_allowlist`/`model_override` significa "limpar"
    (sentinelizado no use case); ausência da chave no JSON também é
    tolerada — o use case `UpdateAgentProfile` diferencia via `UNSET`.
    `name`, `system_prompt` e `tier` mantêm o valor atual quando ausentes.
    """

    name: str | None = Field(None, min_length=1, max_length=200)
    system_prompt: str | None = Field(None, min_length=1)
    skills_allowlist: list[str] | None | Any = None
    tools_allowlist: list[str] | None | Any = None
    mcp_allowlist: list[str] | None | Any = None
    tier: int | None = Field(None, ge=1, le=4)
    model_override: str | None | Any = None


def _profile_to_out(p: AgentProfile) -> AgentProfileOut:
    """Mapeia `AgentProfile` (domínio) em `AgentProfileOut` (HTTP).

    Isolei o mapeamento para que mudanças de schema (ex.: trocar `str`
    por `datetime`, adicionar campos) fiquem num só ponto e não vazem
    para os endpoints. Datas viram ISO-8601 (preserva `tzinfo`); um
    perfil nunca arquivado serializa `archived_at=None`.
    """
    return AgentProfileOut(
        id=p.id,
        user_id=p.user_id,
        name=p.name,
        slug=p.slug,
        system_prompt=p.system_prompt,
        skills_allowlist=p.skills_allowlist,
        tools_allowlist=p.tools_allowlist,
        mcp_allowlist=p.mcp_allowlist,
        tier=p.tier,
        model_override=p.model_override,
        is_active=p.is_active,
        archived_at=p.archived_at.isoformat() if p.archived_at else None,
        created_at=p.created_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
    )


def _require_user(user: User | None) -> User:
    """Garante um `User` autenticado e o devolve aos endpoints.

    `require_auth` devolve `User | None` (nunca levanta para paths em
    `PUBLIC_PATHS`); este router não tem path público, então `None`
    aqui só aconteceria por bug de injeção. Defesa em profundidade:
    também rejeita `user.id` vazio, que faria o escopo dos use cases
    falhar silenciosamente em alguns bancos.
    """
    if user is None or not user.id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
        )
    return user


# ---------- Router ---------- #


router = APIRouter(prefix="/api/agent-profiles", tags=["agent-profiles"])


@router.post(
    "",
    response_model=AgentProfileOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_profile(
    payload: AgentProfileCreateIn,
    user: Annotated[User | None, Depends(require_auth)],
    use_case: Annotated[
        CreateAgentProfile, Depends(_create_agent_profile_use_case)
    ],
) -> AgentProfileOut:
    """Cria um `AgentProfile` do usuário autenticado (REQ-001).

    `(user_id, slug)` é a chave natural: conflito → 409. Falha de
    validação no domínio (slug fora de kebab-case, `name`/
    `system_prompt` vazios, `tier` fora de `1..4`) → 422.
    """
    actor = _require_user(user)
    try:
        profile = await use_case.execute(
            user_id=actor.id,
            name=payload.name,
            slug=payload.slug,
            system_prompt=payload.system_prompt,
            skills_allowlist=payload.skills_allowlist,
            tools_allowlist=payload.tools_allowlist,
            mcp_allowlist=payload.mcp_allowlist,
            tier=payload.tier,
            model_override=payload.model_override,
        )
    except DuplicateAgentProfileError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except DomainError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _profile_to_out(profile)


@router.get("", response_model=list[AgentProfileOut])
async def list_agent_profiles(
    user: Annotated[User | None, Depends(require_auth)],
    use_case: Annotated[
        ListAgentProfiles, Depends(_list_agent_profiles_use_case)
    ],
    include_archived: Annotated[bool, Query()] = False,
) -> list[AgentProfileOut]:
    """Lista perfis do usuário autenticado (REQ-002).

    `include_archived=false` (default) esconde perfis arquivados
    (soft-deleted); passe `true` para listar tudo, inclusive
    arquivados. Ordenação e paginação ficam para iteração futura — o
    volume esperado é baixo (dezenas, não milhares) e a spec v1 não
    exige.
    """
    actor = _require_user(user)
    profiles = await use_case.execute(
        user_id=actor.id, include_archived=include_archived
    )
    return [_profile_to_out(p) for p in profiles]


@router.get("/{profile_id}", response_model=AgentProfileOut)
async def get_agent_profile(
    profile_id: str,
    user: Annotated[User | None, Depends(require_auth)],
    use_case: Annotated[GetAgentProfile, Depends(_get_agent_profile_use_case)],
) -> AgentProfileOut:
    """Obtém um perfil próprio (REQ-003).

    Cross-user e id inexistente recebem 404 — mesma defesa de não
    revelar existência usada em CRM/Email.
    """
    actor = _require_user(user)
    profile = await use_case.execute(user_id=actor.id, profile_id=profile_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent profile not found",
        )
    return _profile_to_out(profile)


@router.patch("/{profile_id}", response_model=AgentProfileOut)
async def update_agent_profile(
    profile_id: str,
    payload: AgentProfileUpdateIn,
    user: Annotated[User | None, Depends(require_auth)],
    use_case: Annotated[
        UpdateAgentProfile, Depends(_update_agent_profile_use_case)
    ],
) -> AgentProfileOut:
    """Atualiza campos mutáveis de um perfil próprio (REQ-004).

    Cross-user e id inexistente → 404. Erro de domínio (`name`/
    `system_prompt` vazio, `tier` fora de `1..4`) → 422. Os campos
    com sentinel (`skills_allowlist`/`tools_allowlist`/`mcp_allowlist`/
    `model_override`) aceitam `None` para "limpar"; ausência da chave no
    JSON também é tolerada (o use case trata `None` enviado vs `UNSET`
    default separadamente).
    """
    actor = _require_user(user)
    try:
        profile = await use_case.execute(
            user_id=actor.id,
            profile_id=profile_id,
            name=payload.name,
            system_prompt=payload.system_prompt,
            skills_allowlist=payload.skills_allowlist,
            tools_allowlist=payload.tools_allowlist,
            mcp_allowlist=(
                payload.mcp_allowlist
                if "mcp_allowlist" in payload.model_fields_set
                else UNSET
            ),
            tier=payload.tier,
            model_override=payload.model_override,
        )
    except DomainError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent profile not found",
        )
    return _profile_to_out(profile)


@router.post("/{profile_id}/archive", response_model=AgentProfileOut)
async def archive_agent_profile(
    profile_id: str,
    user: Annotated[User | None, Depends(require_auth)],
    use_case: Annotated[
        ArchiveAgentProfile, Depends(_archive_agent_profile_use_case)
    ],
) -> AgentProfileOut:
    """Soft-delete: marca o perfil como arquivado (REQ-005).

    Cross-user e id inexistente → 404. Idempotente (arquivar duas
    vezes deixa o perfil já arquivado e devolve o estado atual).
    Não há `DELETE` por design — a exclusão é sempre lógica para
    preservar histórico de uso.
    """
    actor = _require_user(user)
    profile = await use_case.execute(user_id=actor.id, profile_id=profile_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent profile not found",
        )
    return _profile_to_out(profile)


@router.delete("/{profile_id}")
async def delete_agent_profile_unsupported(profile_id: str) -> None:
    """`DELETE` deliberadamente não suportado — devolve 405 com hint.

    Cliente que tenta `DELETE /api/agent-profiles/{id}` recebe 405
    com a mensagem apontando o endpoint correto
    (`POST .../{id}/archive`). Evita o "deletou e sumiu" acidental,
    que seria irreversível em v1 sem endpoint de unarchive.
    """
    del profile_id
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Use POST /api/agent-profiles/{id}/archive instead.",
    )
