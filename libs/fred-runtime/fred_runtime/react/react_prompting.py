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
from datetime import UTC, datetime

from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.models import ReActAgentDefinition

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
