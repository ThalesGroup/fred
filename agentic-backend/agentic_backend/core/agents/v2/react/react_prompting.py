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

from datetime import UTC, datetime

from ..contracts.context import BoundRuntimeContext
from ..contracts.models import ReActAgentDefinition


def safe_prompt_token_map(
    binding: BoundRuntimeContext, *, agent_id: str
) -> dict[str, str]:
    """
    Build the safe prompt-template variables for one ReAct-style runtime call.

    Why this exists:
    - prompt templates often need concrete values such as `today`,
      `response_language`, `session_id`, and `user_id`
    - keeping that mapping in one helper makes it obvious which runtime values are
      allowed to appear in prompts

    How to use:
    - call this before formatting a prompt template that contains placeholders like
      `{today}` or `{response_language}`

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


class _LiteralFriendlyDict(dict[str, str]):
    """
    Preserve unknown prompt placeholders as literals during template rendering.

    Why this exists:
    - a template may still contain a placeholder such as `{question}` or
      `{document_name}` that is not provided by the runtime prompt values
    - preserving the placeholder text avoids a `KeyError` and makes the missing
      value visible in the rendered prompt

    How to use:
    - create through `render_prompt_template(...)`; callers should not need to use
      this class directly

    Example:
    - `template.format_map(_LiteralFriendlyDict({"agent_id": "custodian"}))`
    """

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render_prompt_template(
    template: str, *, binding: BoundRuntimeContext, agent_id: str
) -> str:
    """
    Render one ReAct-style system prompt template with runtime-safe variables.

    Why this exists:
    - agent definitions store prompt templates such as
      `"Today is {today}. Respond in {response_language}."`
    - formatting should stay centralized so ReAct and Deep produce the same final
      prompt text

    How to use:
    - pass the template plus the active bound runtime context and agent id

    Example:
    - `render_prompt_template(template, binding=binding, agent_id="custodian")`
    """

    return template.format_map(
        _LiteralFriendlyDict(safe_prompt_token_map(binding, agent_id=agent_id))
    )


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
