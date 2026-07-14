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
get formatted into the prompt, decided by matching each skill's own
`name`/`description` text (which already documents its own trigger
keywords) against the recent conversation. Adding a new skill needs zero
code changes here — unlike modes, this is O(1) per skill, not O(n).
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

from deepagents.middleware._utils import append_to_system_message
from deepagents.middleware.skills import SkillMetadata, SkillsMiddleware

if TYPE_CHECKING:
    from langchain.agents.middleware.types import ContextT, ModelRequest
    from langchain_core.messages import AnyMessage

_WORD_RE = re.compile(r"[a-z0-9]+")
_MIN_TOKEN_LEN = 4
_MAX_RECENT_HUMAN_MESSAGES = 6


def _tokens(text: str) -> set[str]:
    """Lowercase, alnum-only tokens of at least `_MIN_TOKEN_LEN` chars."""
    return {w for w in _WORD_RE.findall(text.lower()) if len(w) >= _MIN_TOKEN_LEN}


def _recent_human_text(messages: list[AnyMessage]) -> str:
    """Join the text of the last few human turns (tool/AI noise excluded)."""
    human_texts = [str(m.text) for m in messages if getattr(m, "type", None) == "human"]
    return " ".join(human_texts[-_MAX_RECENT_HUMAN_MESSAGES:])


def _filter_relevant_skills(
    skills: list[SkillMetadata], messages: list[AnyMessage]
) -> list[SkillMetadata]:
    """Keep only skills whose name/description overlaps the recent conversation.

    Fails open (returns `skills` unchanged) when there's no conversation yet,
    or when the keyword match would hide everything. An imperfect filter
    that never fully hides discovery is safer than a tighter one that
    sometimes does — required by `skills-3`'s "no relevant skill goes
    undiscovered" acceptance criterion.
    """
    convo_tokens = _tokens(_recent_human_text(messages))
    if not convo_tokens:
        return skills

    relevant = [
        skill
        for skill in skills
        if convo_tokens & _tokens(f"{skill['name']} {skill['description']}")
    ]
    return relevant if relevant else skills


class ScopedSkillsMiddleware(SkillsMiddleware):
    """`SkillsMiddleware` that injects only the conversation-relevant skills.

    Same constructor and skill-loading behavior as the base class
    (`before_agent`/`abefore_agent` are untouched) — only the system-prompt
    injection in `modify_request` is scoped.
    """

    def modify_request(self, request: ModelRequest[ContextT]) -> ModelRequest[ContextT]:
        """Inject only the skills relevant to `request.messages` into the system prompt."""
        skills_metadata = cast("list[SkillMetadata]", request.state.get("skills_metadata", []))
        skills_load_errors = cast("list[str]", request.state.get("skills_load_errors", []))
        relevant = _filter_relevant_skills(skills_metadata, request.messages)

        skills_section = self.system_prompt_template.format(
            skills_locations=self._format_skills_locations(),
            skills_load_warnings=self._format_skills_load_warnings(skills_load_errors),
            skills_list=self._format_skills_list(relevant),
        )
        new_system_message = append_to_system_message(request.system_message, skills_section)
        return request.override(system_message=new_system_message)


__all__ = ["ScopedSkillsMiddleware"]
