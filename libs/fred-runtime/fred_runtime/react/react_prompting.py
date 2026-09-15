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
from fred_sdk.resources.prompts import GLOBAL_BASE_PROMPT_MARKDOWN

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


# Matches only a real filename extension — the extension must be followed by
# the attachment line's own terminator (" [uid]", ": description", or
# end-of-string), not just any non-word character. A plain `\b` would also
# match e.g. "export.csv.bak" (word boundary between "v" and "."), annotating
# a line the actual `.csv` tabular-build gate in `fast_ingest`
# (`filename.lower().endswith(".csv")`) would never match.
_FILENAME_TERMINATOR = r"(?=[\s:\[]|$)"
_CSV_ATTACHMENT_RE = re.compile(rf"\.csv{_FILENAME_TERMINATOR}", re.IGNORECASE)
_CSV_ATTACHMENT_NOTE = (
    " (SQL-queryable dataset ONLY, not indexed for search - never call the "
    "conversation search tool for this id, use the tabular/SQL tools for "
    "everything about it, including keyword/value lookups)"
)
# Used instead of `_CSV_ATTACHMENT_NOTE` when the calling agent instance has
# no tabular MCP tool bound (see `tabular_tools_bound` /
# `tabular_tools_available` below) — telling the model to call a tool it does
# not have would just produce a tool-not-found error.
_CSV_ATTACHMENT_NOTE_NO_TOOLS = (
    " (a SQL-queryable dataset was built for this file, but no tabular/SQL "
    "tool is enabled for this assistant - you cannot query or search it; "
    "tell the user their assistant needs tabular/SQL capability enabled to "
    "analyze this file)"
)
# `xls[xm]?` covers .xls, .xlsx, and .xlsm — all three are real configured
# attachment suffixes (FastSpreadsheetProcessor).
_EXCEL_ATTACHMENT_RE = re.compile(rf"\.xls[xm]?{_FILENAME_TERMINATOR}", re.IGNORECASE)
_EXCEL_ATTACHMENT_NOTE = (
    " (markdown text, NOT a SQL dataset - use the conversation search tool, "
    "never the tabular/SQL tools)"
)


def build_attachment_context_suffix(
    binding: BoundRuntimeContext, *, tabular_tools_available: bool
) -> str:
    """
    Render current conversation attachments as a per-turn system-prompt suffix.

    The frontend rebuilds ``attachments_markdown`` from current attachment state.
    Deriving this suffix on every invocation means deleting the final attachment
    removes the notice instead of leaving a checkpointed system message behind.

    ``tabular_tools_available`` (see `react_tool_binding.tabular_tools_bound`)
    must reflect whether the *calling agent instance* actually has the
    tabular MCP server bound — the general-purpose agent template ships with
    no default capabilities, so a CSV attachment's SQL dataset can exist
    while this agent has no tool to query it. Telling the model to use a tool
    it doesn't have would just produce a tool-not-found error instead of a
    straight answer to the user.
    """

    attachments_markdown = binding.runtime_context.attachments_markdown
    if not attachments_markdown or not attachments_markdown.strip():
        return ""
    safe_attachment_lines = [
        line
        for line in attachments_markdown.splitlines()
        if not line.lstrip().startswith("data:")
    ]

    # A paragraph-level rule alone was ignored in live testing (the model
    # still fed an attachment uid to the wrong tool). Models weigh an
    # annotation glued to the data far more than a distant instruction, so
    # repeat it on each CSV/Excel line, right next to the uid the model would
    # pass to those tools. CSV attachments are real SQL-queryable datasets
    # (DESIGN.md, "Session-Scoped Attachment Datasets") — only Excel still
    # gets the "text only" annotation.
    def _annotate(line: str) -> str:
        if not line.lstrip().startswith("-"):
            return line
        if _CSV_ATTACHMENT_RE.search(line):
            note = (
                _CSV_ATTACHMENT_NOTE
                if tabular_tools_available
                else _CSV_ATTACHMENT_NOTE_NO_TOOLS
            )
            return f"{line}{note}"
        if _EXCEL_ATTACHMENT_RE.search(line):
            return f"{line}{_EXCEL_ATTACHMENT_NOTE}"
        return line

    safe_attachment_lines = [_annotate(line) for line in safe_attachment_lines]
    safe_attachments_markdown = escape_reserved_prompt_tags(
        "\n".join(safe_attachment_lines).strip()
    )
    if not safe_attachments_markdown:
        return ""
    csv_capability_sentence = (
        "Pass a CSV attachment's uid to the tabular/SQL "
        "tools for everything about it: exact counts, filters, or aggregates, and "
        "keyword/value lookups too (e.g. search_tabular_values), not only "
        "aggregate questions."
        if tabular_tools_available
        else "No tabular/SQL tool is enabled for this assistant, so a CSV "
        "attachment's data cannot be queried or searched at all in this "
        "session - say so plainly instead of guessing at its contents."
    )
    return (
        "\n\nThe user has attached one or more files to this conversation. "
        "Treat them as scoped to the current conversation and the current user's "
        "authorized access only. Every attached file except CSV — documents AND "
        "images — has been ingested and indexed for retrieval: its text (for an "
        "image, an extracted vision description) is searchable through your "
        "knowledge/document search tool, scoped to this conversation. The raw "
        "image bytes are NOT included in this prompt, so to answer any question "
        "about an attached file you MUST first call the search tool to retrieve "
        "its content — do not claim you cannot see or analyze an attachment "
        "before searching for it. CSV attachments are the one exception: they "
        "are NOT indexed for search at all, only as a SQL-queryable dataset — "
        "the conversation search tool will find nothing for a CSV attachment, so "
        f"never call it for one. {csv_capability_sentence} "
        "Excel attachments (XLS, XLSX) are text only for "
        "now: they are NOT loaded as SQL-queryable tables, so never pass their "
        "uid to the tabular/SQL tools - retrieve their content through the "
        "search tool. "
        "When a file line below shows a bracketed identifier, that is the "
        "file's internal document uid: pass exactly that value — never the "
        "file name — to document tools that take a document_uid (e.g. "
        "summarize_document). These identifiers are internal working ids: "
        "NEVER repeat them in your answers — always refer to files by their "
        "display name.\n\n"
        f"{safe_attachments_markdown}"
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
    tabular_tools_available: bool,
) -> str:
    """
    Assemble the system prompt shared by the ReAct and Deep runtimes.

    Four XML-wrapped blocks whose order is also their precedence (the clause
    lives in the platform instructions), then the untagged per-turn context:
    selected prompts, document scope, attachments. Full rationale:
    PROMPTS.md "System Prompt Assembly".

    ``tool_suffix`` is everything the model must know about its tools this
    turn (list, MCP instructions, runtime notices); the shared output contract
    is appended to it here. ``tabular_tools_available`` must come from
    `react_tool_binding.tabular_tools_bound(bound_tools)` for this call's
    resolved tools.
    """

    tools_content = "\n\n".join(
        part for part in (tool_suffix.strip(), GLOBAL_BASE_PROMPT_MARKDOWN) if part
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
    per_turn = (
        build_context_prompt_suffix(binding, agent_id=agent_id),
        build_document_scope_suffix(binding),
        build_attachment_context_suffix(
            binding, tabular_tools_available=tabular_tools_available
        ),
    )
    return "\n\n".join(block for block in rendered if block) + "".join(per_turn)
