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

import re
from collections.abc import Sequence
from datetime import UTC, datetime

from fred_sdk.contracts.context import BoundRuntimeContext
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
    Render the platform-wide platform prompt — the FIRST block of the system prompt.

    Why this exists:
    - a platform admin needs one place to state how every agent on the
      deployment must behave, ahead of any agent's own template. Before this,
      the only platform-wide text was the static
      `GLOBAL_BASE_PROMPT_MARKDOWN` output contract, which is shipped in
      fred-sdk and deliberately not editable.
    - it goes first, not last, for the reason §8.67 moved the agent template
      last: this is the single most stable block on a deployment — identical
      for every agent, every session, every turn — so it extends the provider
      prefix cache rather than truncating it. Ordering is not precedence here;
      the output contract that follows is subordinated by its own wording,
      exactly as `build_context_prompt_suffix` already is.

    Precedence:
    - `binding.platform_prompt` (what a platform admin saved, resolved trusted
      per managed turn) wins.
    - `None` means no admin ever saved one — fall back to the shipped
      `platform_prompt` field of the pod's `config/platform_prompt.json`. That
      is the same file control-plane fetches over `GET /agents/platform-prompt`
      to fill the admin editor, so what an admin reads there is what agents
      actually receive.
    - an admin-saved empty string is NOT `None`: it suppresses the block on
      purpose, and must not silently resurrect the shipped default.

    How to use:
    - first element of `compose_system_prompt`'s block list.
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
    # Leading separator, like every other block in `compose_system_prompt`:
    # each one owns the blank line that precedes it, none owns the one that
    # follows. Being first is not an exception — the composer strips the
    # resulting leading newlines once, for whichever block happens to lead.
    return f"\n\n{text.strip()}"


def build_platform_instructions_prefix() -> str:
    """
    Render the platform's operating instructions — the SECOND block, directly
    under the admin-editable platform prompt.

    Why this exists:
    - the platform prompt above it carries personality and deployment-specific
      intent, and an admin can rewrite it freely. The behaviour a coherent
      platform depends on — call the tools you were given, never fake a call,
      recover from a failed one, say when you don't know — must not be
      rewritable along with it, so it lives here, shipped and read-only.
    - it absorbed `build_tool_failure_recovery_suffix`'s hardcoded text
      (removed 2026-08-31). That guidance was the same kind of rule living in a
      third place; keeping it separate would have meant the admin UI's
      "platform instructions" view showed only part of what agents are actually
      told, which is worse than not showing it at all.

    Not the same thing as `build_global_base_prompt_suffix` below: that one is
    an OUTPUT/renderer contract (Mermaid syntax) and stays after the platform blocks.
    This one is operating behaviour and leads the prompt with the platform
    prompt, where the two platform-wide layers read as one section.

    How to use:
    - second element of `compose_system_prompt`'s block list.
    """

    runtime_context = get_runtime_context_or_none()
    text = (
        runtime_context.get_platform_instructions()
        if runtime_context is not None
        else None
    )
    if text is None or not text.strip():
        return ""
    return f"\n\n{text.strip()}"


def build_global_base_prompt_suffix() -> str:
    """
    Render Fred's shared global base prompt as a runtime system-prompt suffix.

    Why this exists:
    - renderer/output contracts (currently the Mermaid output contract) must apply
      to every ReAct/Deep agent turn, but they should NOT live inside the
      operator-editable ``system_prompt_template`` where they clutter the agent
      editor and an operator can accidentally delete them
    - injecting the contract at execution time keeps one source of truth
      (``GLOBAL_BASE_PROMPT_MARKDOWN``) and guarantees it is present even when the
      operator overrides the whole prompt — the previous authoring-time bake lost
      the contract on any custom prompt

    How to use it:
    - append the returned text during final system-prompt composition, after
      the platform blocks (see `compose_system_prompt`)

    Example:
    - `system_prompt += build_global_base_prompt_suffix()`
    """

    if not GLOBAL_BASE_PROMPT_MARKDOWN.strip():
        return ""
    return f"\n\n{GLOBAL_BASE_PROMPT_MARKDOWN}"


def build_attachment_context_suffix(binding: BoundRuntimeContext) -> str:
    """
    Render current conversation attachments as a per-turn system-prompt suffix.

    The frontend rebuilds ``attachments_markdown`` from current attachment state.
    Deriving this suffix on every invocation means deleting the final attachment
    removes the notice instead of leaving a checkpointed system message behind.
    """

    attachments_markdown = binding.runtime_context.attachments_markdown
    if not attachments_markdown or not attachments_markdown.strip():
        return ""
    safe_attachment_lines = [
        line
        for line in attachments_markdown.splitlines()
        if not line.lstrip().startswith("data:")
    ]
    safe_attachments_markdown = "\n".join(safe_attachment_lines).strip()
    if not safe_attachments_markdown:
        return ""
    return (
        "\n\nThe user has attached one or more files to this conversation. "
        "Treat them as scoped to the current conversation and the current user's "
        "authorized access only. Every attached file — documents AND images — has "
        "been ingested and indexed for retrieval: its text (for an image, an "
        "extracted vision description) is searchable through your knowledge/document "
        "search tool, scoped to this conversation. The raw image bytes are NOT "
        "included in this prompt, so to answer any question about an attached file "
        "you MUST first call the search tool to retrieve its content — do not claim "
        "you cannot see or analyze an attachment before searching for it. "
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
    listed = "\n".join(f"- {uid}" for uid in uids)
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
    rendered = render_prompt_template(
        context_prompt_text, binding=binding, agent_id=agent_id
    ).strip()
    if not rendered:
        return ""
    return (
        "\n\nThe following instructions were selected for this conversation. Follow "
        "them for every response where they do not conflict with the platform "
        "instructions or the output contract above:\n\n"
        f"{rendered}"
    )


def compose_system_prompt(
    base_prompt: str,
    *,
    binding: BoundRuntimeContext,
    agent_id: str,
    tool_suffix: str = "",
    runtime_suffixes: Sequence[str] = (),
) -> str:
    """
    Assemble the final system prompt shared by the ReAct and Deep runtimes.

    Why this exists:
    - both runtimes need the identical block chain (the two platform-wide
      blocks, global base contract, tools, then the per-turn conversation
      context: selected prompts and attachments). Each runtime
      used to hand-roll that chain, and they had already drifted — attachments
      reached ReAct but not Deep, and neither injected the selected chat-context
      prompts (#1915). One owner keeps them from drifting again.

    Ordering rationale (issue #2412 item 3, 2026-08-27 — supersedes the
    "agent template first" chain this function shipped with; extended
    2026-08-31 with the two platform blocks):
    - **The platform** — ``build_platform_prompt_prefix`` (admin-editable
      personality and standardised instructions), then
      ``build_platform_instructions_prefix`` (shipped, read-only operating
      behaviour). The most stable text on a deployment: identical for every
      agent, every session, every turn, so it extends the provider prefix
      cache rather than truncating it. Read as one section, which is why they
      are adjacent.
    - **General instructions** — the global base output contract. A hard
      invariant, identical across every agent on a deployment. (Two blocks
      used to sit here: tool-failure recovery, folded into the platform
      instructions, and per-agent guardrails, folded into each agent's
      template — RUNTIME-EXECUTION-CONTRACT §8.70/§8.71.)
    - **Tools** — ``tool_suffix``: what tools exist, grouped by MCP server
      with each server's ``agent_instructions`` inlined (#2455). Also
      near-identical across agents sharing the same tool set.
    - **Tool usage** — ``runtime_suffixes``: runtime-specific static notices
      (e.g. Deep's filesystem-browsing context). Rare enough today to still
      sit ahead of the agent block rather than needing its own numbered slot.
    - **The agent** — ``base_prompt``, the rendered agent template, preceded
      by a fixed ``# Agent instructions`` heading (#2412 item 3 follow-up,
      2026-08-28) so the boundary is visible: without it, ``base_prompt``
      landed directly after the tool/``agent_instructions`` block above with
      no blank line or marker, making it hard to tell where Fred's shared
      instructions end and this agent's own configured behavior begins. The
      LAST *static* block: for a given agent instance, everything before it
      is identical turn over turn (and largely identical across agents
      sharing the deployment's tools), while the agent's own
      instructions are what should carry the model's attention. Two reasons,
      not just one: recency (the model's own instructions are furthest from
      its answer under the old order) and provider prefix-cache reuse (the
      stable prefix — general instructions + tools — now extends all the way
      to the agent block instead of ending after the first few dozen
      characters).
    - **Per-turn user context, unchanged** — selected chat-context prompts,
      then the turn's document scope, then conversation attachments. Placed
      last because they are genuinely volatile (change with the conversation,
      not just the agent), which also keeps the cache boundary clean:
      everything before this point is stable for the whole session.

    How to use:
    - render the agent template first, then pass it here with the runtime's tool
      suffix and any runtime-specific suffixes.
    """

    # No dangling heading when an agent has no configured template at all
    # (`policy.system_prompt_template or ""` in the callers) — only mark the
    # boundary when there is a template to introduce.
    agent_header = "\n\n# Agent instructions\n\n" if base_prompt.strip() else ""

    # `.lstrip("\n")`: every block carries its own leading blank line, so
    # whichever one comes first would otherwise open the prompt with stray
    # newlines.
    return "".join(
        [
            build_platform_prompt_prefix(binding),
            build_platform_instructions_prefix(),
            build_global_base_prompt_suffix(),
            tool_suffix,
            *runtime_suffixes,
            agent_header,
            base_prompt,
            build_context_prompt_suffix(binding, agent_id=agent_id),
            build_document_scope_suffix(binding),
            build_attachment_context_suffix(binding),
        ]
    ).lstrip("\n")
