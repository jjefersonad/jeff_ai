"""`SkillsMiddleware` variant that scopes the injected skill listing to the conversation.

Task `unified-agent-realignment-task-ctx-2` (design Q8, part 2/2). The stock
`SkillsMiddleware` lists every loaded skill's name + description on **every**
turn regardless of relevance — 11 skills today, ~19.8k system-prompt chars
measured in task `skills-3`, unrelated to what the conversation is actually
about (a pure-SDD question still pays for `pptx`/`xlsx`/`docx`/
`brand-guidelines`).

This is **not** a resurrection of the removed mode system
(`classify_mode()`/`_MODE_PATTERNS`, task `modes-1`): there is no fixed
category enum, and neither the tool set nor the base prompt changes. The
only thing that varies is which entries of the *already-loaded* skill list
get formatted into the prompt, decided by embedding-based cosine similarity
between each skill's own `name`/`description` text and the recent
conversation (change `semantic-skill-relevance-filtering` — replaces an
earlier exact-lowercase-token-overlap filter, which silently failed for any
skill whose description wasn't written in the same language as the
conversation). Adding a new skill needs zero code changes here — unlike
modes, this is O(1) per skill, not O(n).
"""
from __future__ import annotations

import hashlib
import logging
import os
from typing import TYPE_CHECKING, Awaitable, Callable, NotRequired, cast

import numpy as np
from deepagents.middleware._utils import append_to_system_message
from deepagents.middleware.skills import (
    SkillMetadata,
    SkillsMiddleware,
    SkillsState,
    SkillsStateUpdate,
)
from langchain.agents.middleware.types import PrivateStateAttr
from typing_extensions import Annotated

from src.models.ollama_embeddings import aembed_texts, embed_texts

if TYPE_CHECKING:
    from langchain.agents.middleware.types import ContextT, ModelRequest
    from langchain_core.messages import AnyMessage
    from langchain_core.runnables import RunnableConfig
    from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

_MAX_RECENT_HUMAN_MESSAGES = 6

# Cache em memória, chaveado por hash do conteúdo (`name`+`description`) de
# cada skill: embeddar 13 textos curtos é barato, mas não há razão para
# refazer a chamada de rede ao Ollama a cada turno para skills cujo SKILL.md
# não mudou desde o último processo. Editar um SKILL.md muda o hash e invalida
# a entrada sozinho — não é necessário nenhum mecanismo de invalidação manual.
_skill_embedding_cache: dict[str, list[float]] = {}


def _skill_content_hash(skill: SkillMetadata) -> str:
    """Hash estável do conteúdo relevante de uma skill para fins de cache."""
    content = f"{skill['name']} {skill['description']}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _get_or_embed_skill(
    skill: SkillMetadata, embed_fn: Callable[[list[str]], list[list[float]]]
) -> list[float]:
    """Retorna o embedding cacheado de uma skill, calculando-o na primeira vez.

    `embed_fn` recebe uma lista de textos e devolve a lista de vetores
    correspondente (mesma assinatura de `embed_texts`/`aembed_texts` já usada
    para a memória) — passado como parâmetro para não acoplar este cache a um
    caminho sync ou async específico.
    """
    content_hash = _skill_content_hash(skill)
    cached = _skill_embedding_cache.get(content_hash)
    if cached is not None:
        return cached
    [vector] = embed_fn([f"{skill['name']} {skill['description']}"])
    _skill_embedding_cache[content_hash] = vector
    return vector


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Similaridade de cosseno entre dois vetores; 0.0 se algum for nulo."""
    a_arr = np.asarray(a, dtype=float)
    b_arr = np.asarray(b, dtype=float)
    denom = float(np.linalg.norm(a_arr) * np.linalg.norm(b_arr))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / denom)


# Limiar de similaridade de cosseno abaixo do qual uma skill é considerada
# irrelevante. Calibrado empiricamente: embeddings REAIS via Ollama
# (mxbai-embed-large) das 14 skills reais do projeto contra 10 prompts
# representativos (PT+EN, um por skill-alvo + 3 neutros) — task
# `semantic-skill-relevance-filtering-task-calibration-1`.
#
# Achado real da calibração: não existe limiar com precisão perfeita — a
# similaridade da skill CERTA para um prompt (ex.: `pptx` para "monta uma
# apresentação de slides", 0.5377) pode ficar abaixo da similaridade de uma
# skill ERRADA para outro prompt (ex.: `document-memory` para "crie um
# documento word", 0.6694). As distribuições de "deveria aparecer" e "não
# deveria aparecer" se sobrepõem com este modelo de embedding. 0.5 foi
# escolhido para garantir zero falso-negativo nos 7 pares prompt/skill-alvo
# testados (a skill certa sempre cruza o limiar), aceitando que skills extras
# frouxamente relacionadas às vezes também apareçam — o mesmo trade-off
# recall-first que já motivava o fail-open desta feature.
_DEFAULT_SKILL_RELEVANCE_THRESHOLD = 0.5


def _skill_relevance_threshold() -> float:
    """Limiar de relevância, sobrescrevível via `SKILL_RELEVANCE_THRESHOLD`."""
    raw = os.getenv("SKILL_RELEVANCE_THRESHOLD")
    if raw is None:
        return _DEFAULT_SKILL_RELEVANCE_THRESHOLD
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "SKILL_RELEVANCE_THRESHOLD=%r não é um float válido; usando o default %s",
            raw,
            _DEFAULT_SKILL_RELEVANCE_THRESHOLD,
        )
        return _DEFAULT_SKILL_RELEVANCE_THRESHOLD


def _compute_relevant_skill_names(
    skills: list[SkillMetadata],
    conversation_text: str,
    embed_fn: Callable[[list[str]], list[list[float]]],
) -> list[str] | None:
    """Nomes das skills relevantes a `conversation_text`, ou `None` para fail-open.

    Fail-open (mostrar todas) em dois casos: o embedding falhou (ex.: Ollama
    fora do ar) ou nenhuma skill cruzou `_skill_relevance_threshold()` — a
    mesma garantia que o antigo filtro por token dava para o caso "sem overlap".
    """
    if not skills or not conversation_text.strip():
        return None
    try:
        threshold = _skill_relevance_threshold()
        [conversation_vector] = embed_fn([conversation_text])
        relevant = [
            skill["name"]
            for skill in skills
            if cosine_similarity(conversation_vector, _get_or_embed_skill(skill, embed_fn))
            >= threshold
        ]
    except Exception:
        logger.warning(
            "Skill relevance embedding failed; failing open (showing all skills)",
            exc_info=True,
        )
        return None
    return relevant or None


async def _aget_or_embed_skill(
    skill: SkillMetadata, aembed_fn: Callable[[list[str]], Awaitable[list[list[float]]]]
) -> list[float]:
    """Contraparte async de `_get_or_embed_skill` — mesmo cache, sem bloquear o event loop."""
    content_hash = _skill_content_hash(skill)
    cached = _skill_embedding_cache.get(content_hash)
    if cached is not None:
        return cached
    [vector] = await aembed_fn([f"{skill['name']} {skill['description']}"])
    _skill_embedding_cache[content_hash] = vector
    return vector


async def _acompute_relevant_skill_names(
    skills: list[SkillMetadata],
    conversation_text: str,
    aembed_fn: Callable[[list[str]], Awaitable[list[list[float]]]],
) -> list[str] | None:
    """Contraparte async de `_compute_relevant_skill_names`."""
    if not skills or not conversation_text.strip():
        return None
    try:
        threshold = _skill_relevance_threshold()
        [conversation_vector] = await aembed_fn([conversation_text])
        relevant = [
            skill["name"]
            for skill in skills
            if cosine_similarity(
                conversation_vector, await _aget_or_embed_skill(skill, aembed_fn)
            )
            >= threshold
        ]
    except Exception:
        logger.warning(
            "Skill relevance embedding failed; failing open (showing all skills)",
            exc_info=True,
        )
        return None
    return relevant or None


class ScopedSkillsState(SkillsState):
    """`SkillsState` estendido com a lista de skills relevantes do turno atual."""

    relevant_skill_names: NotRequired[Annotated[list[str] | None, PrivateStateAttr]]
    """Nomes das skills relevantes ao turno, calculados em `before_agent`/`abefore_agent`.

    `None` (ou ausente) significa "mostrar todas" — tanto no caso de falha no
    cálculo de embedding quanto no caso de nenhuma skill cruzar o limiar de
    similaridade (fail-open, ver REQ-005 de `semantic-skill-relevance`).
    """


class ScopedSkillsStateUpdate(SkillsStateUpdate):
    """`SkillsStateUpdate` estendido com `relevant_skill_names`."""

    relevant_skill_names: NotRequired[list[str] | None]


def _recent_human_text(messages: list[AnyMessage]) -> str:
    """Join the text of the last few human turns (tool/AI noise excluded)."""
    human_texts = [str(m.text) for m in messages if getattr(m, "type", None) == "human"]
    return " ".join(human_texts[-_MAX_RECENT_HUMAN_MESSAGES:])


class ScopedSkillsMiddleware(SkillsMiddleware):
    """`SkillsMiddleware` that injects only the conversation-relevant skills.

    Same constructor as the base class. `before_agent`/`abefore_agent` are
    overridden to additionally compute `relevant_skill_names` (embedding-based
    cosine similarity, see `_compute_relevant_skill_names`) once per turn and
    store it in state; `modify_request` only reads that precomputed value —
    it never triggers an embedding call itself, since it may run multiple
    times per turn (once per internal model-call step of the tool-calling
    loop), and a network call there would both repeat needlessly and risk
    blocking the event loop on the async path (`awrap_model_call` invokes the
    same sync `modify_request`, unlike `before_agent`/`abefore_agent` which
    have a real async variant).
    """

    def before_agent(
        self, state: SkillsState, runtime: Runtime, config: RunnableConfig
    ) -> SkillsStateUpdate | None:
        """Load skills (base behavior) and compute this turn's relevant-skill list."""
        base_update = super().before_agent(state, runtime, config)
        skills_metadata = cast(
            "list[SkillMetadata]",
            base_update["skills_metadata"] if base_update else state.get("skills_metadata", []),
        )
        conversation_text = _recent_human_text(cast("list[AnyMessage]", state.get("messages", [])))
        relevant = _compute_relevant_skill_names(skills_metadata, conversation_text, embed_texts)

        update: ScopedSkillsStateUpdate = dict(base_update) if base_update else {}  # type: ignore[assignment]
        update["relevant_skill_names"] = relevant
        return update

    async def abefore_agent(
        self, state: SkillsState, runtime: Runtime, config: RunnableConfig
    ) -> SkillsStateUpdate | None:
        """Async counterpart of `before_agent` — uses `aembed_texts`, never blocks."""
        base_update = await super().abefore_agent(state, runtime, config)
        skills_metadata = cast(
            "list[SkillMetadata]",
            base_update["skills_metadata"] if base_update else state.get("skills_metadata", []),
        )
        conversation_text = _recent_human_text(cast("list[AnyMessage]", state.get("messages", [])))
        relevant = await _acompute_relevant_skill_names(
            skills_metadata, conversation_text, aembed_texts
        )

        update: ScopedSkillsStateUpdate = dict(base_update) if base_update else {}  # type: ignore[assignment]
        update["relevant_skill_names"] = relevant
        return update

    def modify_request(self, request: ModelRequest[ContextT]) -> ModelRequest[ContextT]:
        """Inject only the skills relevant to the conversation into the system prompt.

        Reads `relevant_skill_names` from state — computed once per turn by
        `before_agent`/`abefore_agent` — instead of recomputing relevance
        here, since this method may run multiple times per turn (once per
        internal model-call step).
        """
        skills_metadata = cast("list[SkillMetadata]", request.state.get("skills_metadata", []))
        skills_load_errors = cast("list[str]", request.state.get("skills_load_errors", []))
        relevant_names = cast("list[str] | None", request.state.get("relevant_skill_names"))
        relevant = (
            [skill for skill in skills_metadata if skill["name"] in relevant_names]
            if relevant_names
            else skills_metadata
        )

        skills_section = self.system_prompt_template.format(
            skills_locations=self._format_skills_locations(),
            skills_load_warnings=self._format_skills_load_warnings(skills_load_errors),
            skills_list=self._format_skills_list(relevant),
        )
        new_system_message = append_to_system_message(request.system_message, skills_section)
        return request.override(system_message=new_system_message)


__all__ = ["ScopedSkillsMiddleware"]
