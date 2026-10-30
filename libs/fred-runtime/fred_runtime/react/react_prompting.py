# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Shared prompt composition helpers for v2 ReAct-style runtimes.

Why this module exists:
- keep prompt rendering concerns out of `react_runtime.py`, which should focus on
  runtime orchestration and event streaming
- let ReAct and Deep share one small, explicit prompt-building surface

How to use:
- import these helpers when a runtime needs to render the final system prompt
  from a definition prompt template plus concrete values such as today's date,
  the response language, the session id, and the user id

Example:
- `system_prompt = render_prompt_template(template, binding=binding, agent_id="custodian")`
"""

from __future__ import annotations

import functools
import re
from datetime import UTC, datetime

from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.prompt_utils import (
    RESERVED_PROMPT_TAGS,
    escape_reserved_prompt_tags,
)

from ..runtime_context import get_runtime_context_or_none

# Matches only {simple_identifier} — same pattern as the validator so the two
# surfaces stay in sync. Non-simple patterns ({}, {0}, {x.y}) are not touched.
_SIMPLE_TOKEN_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def safe_prompt_token_map(
    binding: BoundRuntimeContext, *, agent_id: str
) -> dict[str, str]:
    """
    Build the runtime values for the canonical PROMPT_SAFE_TOKENS at call time.

    Why this exists:
    - prompt templates need concrete runtime values for {today}, {response_language},
      {session_id}, {user_id}, and {agent_id}
    - keeping that mapping in one helper makes it obvious which values are injected

    How to use:
    - call this before rendering a prompt template

    Example:
    - `safe_prompt_token_map(binding, agent_id="custodian")`
    """
    response_language = normalize_response_language(binding.runtime_context.language)
    return {
        "agent_id": agent_id,
        "today": datetime.now(tz=UTC).date().isoformat(),
        "response_language": response_language,
        "session_id": binding.runtime_context.session_id or "",
        "user_id": binding.runtime_context.user_id or "",
    }


def render_prompt_template(
    template: str,
    *,
    binding: BoundRuntimeContext,
    agent_id: str,
    extra_tokens: dict[str, str] | None = None,
) -> str:
    """
    Render one ReAct-style system prompt template with runtime-safe substitution.

    Why this exists:
    - agent definitions store prompt templates such as
      `"Today is {today}. Respond in {response_language}."`
    - the renderer is centralized so ReAct and Deep produce the same final prompt

    How to use:
    - pass the template plus the active bound runtime context and agent id
    - extra_tokens is an internal mechanism for SDK-level agent developer templates
      (e.g. prompts.planning injected as prompts_planning); it is not available to
      user-authored prompts submitted via the control-plane UI

    Safety guarantee:
    - only {simple_identifier} patterns present in the merged token map are
      substituted; everything else (code braces, dotted notation, empty braces)
      is preserved as a literal — this function never raises an exception

    Example:
    - `render_prompt_template(template, binding=binding, agent_id="custodian")`
    """
    tokens = safe_prompt_token_map(binding, agent_id=agent_id)
    if extra_tokens:
        tokens = {**tokens, **extra_tokens}

    def _replace(m: re.Match[str]) -> str:
        return tokens.get(m.group(1), m.group(0))

    return _SIMPLE_TOKEN_RE.sub(_replace, template)


def normalize_response_language(language: str | None) -> str:
    """
    Convert one runtime language hint to the human-facing prompt wording.

    Why this exists:
    - prompt templates should say `français` or `English`, not raw values such as
      `fr`, `fr-FR`, or `en_US`
    - one normalizer keeps that wording stable across runtimes

    How to use:
    - pass the language stored in runtime context before inserting it into the
      prompt text

    Example:
    - `normalize_response_language("fr")`
    """

    if not language:
        return "English"
    normalized = language.strip()
    if not normalized:
        return "English"
    key = normalized.lower().replace("_", "-")
    if key.startswith("fr"):
        return "français"
    if key.startswith("en"):
        return "English"
    return normalized


def build_platform_prompt_prefix(binding: BoundRuntimeContext) -> str:
    """
    Content of the `platform_prompt` block: the admin-saved text, else the pod
    default. A saved "" suppresses the block and must not resurrect the default,
    so `None` is checked before emptiness. Design: PROMPTS.md "System Prompt Assembly".
    """

    text = binding.platform_prompt
    if text is None:
        runtime_context = get_runtime_context_or_none()
        text = (
            runtime_context.get_default_platform_prompt()
            if runtime_context is not None
            else None
        )
    if text is None or not text.strip():
        return ""
    return text.strip()


def build_platform_instructions_prefix() -> str:
    """
    Content of the `platform_instructions` block: shipped with the pod, read-only,
    and the home of the precedence clause. Design: PROMPTS.md "System Prompt Assembly".
    """

    runtime_context = get_runtime_context_or_none()
    text = (
        runtime_context.get_platform_instructions()
        if runtime_context is not None
        else None
    )
    if text is None or not text.strip():
        return ""
    return text.strip()


def build_attachment_context_suffix(
    binding: BoundRuntimeContext, *, tabular_tools_available: bool
) -> str:
    """Describe only usable server-bound files, with guidance for bound tools."""
    from fred_runtime.model_routing.turn import current_turn
    from fred_runtime.runtime_support.run_scope import RunScope

    scope = RunScope.current()
    if scope is None or scope.turn_authority is None:
        return ""
    authority = current_turn()
    allowed = frozenset(
        authority.document_context(binding.runtime_context).attachment_ids
    )
    files = [
        item for item in authority.binding.attachments if item.document_id in allowed
    ]
    if not files:
        return ""
    lines = []
    for item in files:
        name = escape_reserved_prompt_tags(" ".join(item.name.splitlines()))
        # File names are data, not Markdown structure or reserved prompt tags.
        name = re.sub(r"([\\`*_{\[\]}])", r"\\\1", name)
        tabular = item.mime in {
            "text/csv",
            "application/csv",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel.sheet.macroenabled.12",
        } or item.name.lower().endswith((".csv", ".xls", ".xlsx", ".xlsm"))
        guidance = (
            "use tabular discovery, description and SQL queries"
            if tabular and tabular_tools_available
            else "tabular processing unavailable: no tabular tool is bound"
            if tabular
            else "use the available document reading and search tools"
        )
        lines.append(f"- {name} [{item.document_id}]: {guidance}")
    return (
        "\n\n## Attached files\n"
        "These files are available within this turn's conversation scope. "
        "For text documents, use the available document tools. "
        "CSV and Excel are tabular datasets; do not assume they are vector-indexed "
        "or that document search can read all rows. "
        + (
            "Use list_tabular_documents, then describe_tabular_documents and the "
            "returned table aliases for SQL queries. "
            if tabular_tools_available
            else "No tabular/SQL tool is enabled for this assistant; CSV and Excel "
            "data cannot be queried in this turn. "
        )
        + "Pass the bracketed document uid to tools, never the filename. "
        "Keep these internal identifiers out of answers; refer to files by name.\n\n"
        + escape_reserved_prompt_tags("\n".join(lines))
    )


def build_document_scope_suffix(binding: BoundRuntimeContext) -> str:
    """
    Tell the model that the user narrowed this turn to specific documents.

    Without it the selection is invisible to the model: it has no referent for
    "read this document", falls back to listing the tree, and asks the user
    which file they mean while exactly one is selected. Derived per turn like
    the attachment suffix, so deselecting removes the notice instead of leaving
    a checkpointed system message behind.

    Uids, not display names: `RuntimeContext` carries the selection as uids
    only, and they are what the document tools take. The model is told never to
    repeat them, as everywhere else.
    """

    uids = binding.runtime_context.selected_document_uids
    if not uids:
        return ""
    listed = escape_reserved_prompt_tags("\n".join(f"- {uid}" for uid in uids))
    return (
        "\n\nThe user has picked the document(s) listed below for this turn. "
        'When they say "this document" or "the document", they mean one of '
        "them - read it rather than asking which file they mean. Pass a listed "
        "value as `document_uid`; these are internal working ids, so NEVER "
        "repeat one in your answer - refer to a document by its display name. "
        "The user may also have selected whole libraries, whose documents are "
        "in scope too and reachable through search and the document tree.\n\n"
        f"{listed}"
    )


def build_context_prompt_suffix(binding: BoundRuntimeContext, *, agent_id: str) -> str:
    """
    Render the session's attached chat-context prompts as a system-prompt suffix.

    Why this exists:
    - the control plane resolves a session's ordered library/default prompts into
      one scalar ``context_prompt_text`` (joined with blank lines) and forwards it
      on ``runtime_context`` (PROMPTS.md §5). Before this suffix existed the value
      reached the agent binding but was never appended to the system prompt, so a
      selected prompt such as "speak Spanish" had no effect on the model (#1915).
    - user-authored context prompts may legitimately use the same safe tokens as
      agent templates (e.g. ``{response_language}``, ``{today}``). They are
      therefore rendered through the same safe renderer rather than appended
      verbatim, so a token in a library prompt substitutes exactly as it would in
      an agent prompt — and any unrecognized ``{…}`` is preserved as written,
      since prompt text is stored without token validation (#2277).

    How to use:
    - call while assembling the final system prompt for one runtime turn; returns
      ``""`` when no prompts are attached so an empty selection adds nothing.
    """

    context_prompt_text = binding.runtime_context.context_prompt_text
    if not context_prompt_text or not context_prompt_text.strip():
        return ""
    # Reaches the model unvalidated (session API, pipelines), so it gets the
    # same neutralisation as the other data-derived blocks.
    rendered = escape_reserved_prompt_tags(
        render_prompt_template(
            context_prompt_text, binding=binding, agent_id=agent_id
        ).strip()
    )
    if not rendered:
        return ""
    return (
        "\n\nThe following instructions were selected for this conversation. Follow "
        "them for every response where they do not conflict with the platform "
        "instructions or the output contract above:\n\n"
        f"{rendered}"
    )


# Prompt order of the four blocks; pinned to the shared reserved-tag list so
# the two cannot drift apart.
_BLOCK_TAGS = (
    "platform_instructions",
    "platform_prompt",
    "tools",
    "agent_instructions",
)
assert _BLOCK_TAGS == RESERVED_PROMPT_TAGS

_HEADING_RE = re.compile(r"^( {0,3})(#{1,6})(?=\s|$)")
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def _demote_heading(match: re.Match[str]) -> str:
    return match.group(1) + "#" * min(len(match.group(2)) + 1, 6)


def demote_markdown_headings(text: str) -> str:
    """
    Push every Markdown heading down one level (`#` -> `##`, capped at six).

    Inside a wrapped block the XML tag is the top level, so level 1 belongs to
    nothing. Fenced code is left alone: `#` there is a comment, not a heading.
    """

    lines: list[str] = []
    open_fence: str | None = None
    for line in text.split("\n"):
        fence = _FENCE_RE.match(line)
        if open_fence is None:
            if fence:
                open_fence = fence.group(1)
            else:
                line = _HEADING_RE.sub(_demote_heading, line)
        elif (
            fence
            and fence.group(1)[0] == open_fence[0]
            and len(fence.group(1)) >= len(open_fence)
        ):
            open_fence = None
        lines.append(line)
    return "\n".join(lines)


@functools.lru_cache(maxsize=128)
def render_prompt_block(tag: str, content: str) -> str:
    """Wrap one system-prompt block in its XML tag; "" when the block is blank.

    Cached: the platform blocks and the output contract are identical on every
    turn of every agent, so their demotion runs once per process, not per turn.
    """

    body = content.strip()
    if not body:
        return ""
    return f"<{tag}>\n{demote_markdown_headings(body)}\n</{tag}>"


def compose_system_prompt(
    base_prompt: str,
    *,
    binding: BoundRuntimeContext,
    agent_id: str,
    tool_suffix: str = "",
    skills_prompt: str = "",
    tabular_tools_available: bool,
) -> str:
    """
    Assemble the system prompt shared by the ReAct and Deep runtimes.

    Four XML-wrapped blocks whose order is also their precedence (the clause
    lives in the platform instructions), then the untagged per-turn context:
    selected prompts, document scope, attachments. Full rationale:
    PROMPTS.md "System Prompt Assembly".

    ``tool_suffix`` is everything the model must know about its tools this
    turn (list, MCP instructions, runtime notices). The optional skills catalog
    advertises metadata; skill bodies enter conversation context only on load.
    ``tabular_tools_available`` must come from
    `react_tool_binding.tabular_tools_bound(bound_tools)` for this call's
    resolved tools.
    """

    document_only_instruction = (
        "For this turn, answer factual questions only from document evidence "
        "retrieved from the enabled sources (conversation attachments and/or "
        "team documents). Do not supplement with general knowledge. If the "
        "documents do not support an answer, say that the information is missing."
        if binding.runtime_context.search_rag_scope == "corpus_only"
        else ""
    )
    tools_content = "\n\n".join(
        part
        for part in (tool_suffix.strip(), skills_prompt, document_only_instruction)
        if part
    )
    contents = (
        build_platform_instructions_prefix(),
        build_platform_prompt_prefix(binding),
        tools_content,
        base_prompt,
    )
    rendered = [
        render_prompt_block(tag, content)
        for tag, content in zip(_BLOCK_TAGS, contents, strict=True)
    ]
    selected_skill_names = ", ".join(
        f"`{selection.name}`" for selection in binding.runtime_context.selected_skills
    )
    skill_selection = (
        "\n\nFor this request, the user explicitly requested these platform skills: "
        f"{selected_skill_names}. Apply the matching catalog procedures before "
        "drafting or using task tools. Read their instructions and required "
        "references with the catalog's declared loading tools unless already "
        "loaded. These names are skills, not tool or subagent names. If a selected "
        "name is absent from the catalog, report it as unavailable."
        if selected_skill_names
        else ""
    )
    per_turn = (
        build_context_prompt_suffix(binding, agent_id=agent_id),
        build_document_scope_suffix(binding),
        build_attachment_context_suffix(
            binding, tabular_tools_available=tabular_tools_available
        ),
        skill_selection,
    )
    return "\n\n".join(block for block in rendered if block) + "".join(per_turn)
