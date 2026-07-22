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
from fred_sdk.contracts.models import ReActAgentDefinition
from fred_sdk.resources.prompts import GLOBAL_BASE_PROMPT_MARKDOWN

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


def build_guardrail_suffix(definition: ReActAgentDefinition) -> str:
    """
    Render the prompt suffix for definition guardrails.

    Why this exists:
    - guardrails are declared on the agent definition, but the model only sees the
      final system prompt
    - one helper turns guardrails into the exact text block appended to that prompt

    How to use:
    - call during prompt composition after the main system prompt template is
      rendered

    Example:
    - `system_prompt += build_guardrail_suffix(definition)`
    """

    guardrails = definition.policy().guardrails
    if not guardrails:
        return ""
    lines = ["", "Operating guardrails:"]
    for guardrail in guardrails:
        lines.append(f"- {guardrail.title}: {guardrail.description}")
    return "\n".join(lines)


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
    - append the returned text during final system-prompt composition, after the
      tool and guardrail suffixes (see ReActRuntime / DeepAgentRuntime)

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
      agent templates (e.g. ``{response_language}``, ``{today}``), which are
      persistence-validated against ``PROMPT_SAFE_TOKENS``. They are therefore
      rendered through the same safe renderer rather than appended verbatim, so a
      token in a library prompt substitutes exactly as it would in an agent prompt.

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
        "them for every response where they do not conflict with your operating "
        "guardrails or the output contract above:\n\n"
        f"{rendered}"
    )


def compose_system_prompt(
    base_prompt: str,
    *,
    binding: BoundRuntimeContext,
    definition: ReActAgentDefinition,
    agent_id: str,
    tool_suffix: str = "",
    runtime_suffixes: Sequence[str] = (),
) -> str:
    """
    Assemble the final system prompt shared by the ReAct and Deep runtimes.

    Why this exists:
    - both runtimes need the identical suffix chain (tools, guardrails, global base
      contract, then the per-turn conversation context: selected prompts and
      attachments). Each runtime used to hand-roll that chain, and they had already
      drifted — attachments reached ReAct but not Deep, and neither injected the
      selected chat-context prompts (#1915). One owner keeps them from drifting again.

    Ordering rationale (last suffix carries the most recency weight for the model):
    - ``base_prompt`` — the rendered agent template
    - ``tool_suffix`` — runtime tool descriptions (passed in; runtime-owned)
    - guardrails, then the global base output contract — hard invariants
    - ``runtime_suffixes`` — runtime-specific system notices (e.g. Deep filesystem)
    - selected chat-context prompts, then conversation attachments — per-turn user
      context, placed last so it is freshest while the envelope in
      ``build_context_prompt_suffix`` still subordinates it to the guardrails above.

    How to use:
    - render the agent template first, then pass it here with the runtime's tool
      suffix and any runtime-specific suffixes.
    """

    return "".join(
        [
            base_prompt,
            tool_suffix,
            build_guardrail_suffix(definition),
            build_global_base_prompt_suffix(),
            *runtime_suffixes,
            build_context_prompt_suffix(binding, agent_id=agent_id),
            build_attachment_context_suffix(binding),
        ]
    )
