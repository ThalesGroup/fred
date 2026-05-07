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
Canonical prompt-template token registry and validation utilities.

Why this module exists:
- define the single source of truth for which {tokens} are supported in
  user-authored system prompts
- provide a validator that control-plane can call before persisting any
  prompt field value, so broken templates are rejected at save time rather
  than crashing the agent at execution time
- let the renderer in fred-runtime import the same token set so the two
  surfaces stay in sync automatically

How to use:
- import PROMPT_SAFE_TOKENS to get the canonical {token} → description map
- call validate_prompt_template(text) before persisting a prompt field;
  an empty return list means the template is safe to store
"""

from __future__ import annotations

import re
from typing import Final

from pydantic import BaseModel

# Matches only {simple_identifier} — no dots, no digits, no spaces, not empty.
# This is the only pattern that can ever be a valid template token.
_SIMPLE_TOKEN_RE: Final = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

# Canonical set of runtime tokens available in user-authored system prompts.
# Key   = token name (used inside {…} in the prompt text).
# Value = human-readable description forwarded to the frontend in error messages.
#
# To add a new supported token: add one entry here. The renderer and validator
# pick it up automatically — no other site needs to change.
PROMPT_SAFE_TOKENS: Final[dict[str, str]] = {
    "today": "ISO-8601 date at execution time (e.g. 2026-05-07)",
    "response_language": "Human-readable response language (e.g. English, français)",
    "session_id": "Active session identifier",
    "user_id": "Authenticated user identifier",
    "agent_id": "Agent definition identifier",
}

# Pre-built hint string included in error messages so users see the full list.
_SUPPORTED_HINT: Final[str] = ", ".join(f"{{{k}}}" for k in PROMPT_SAFE_TOKENS)


class PromptTemplateError(BaseModel):
    """One validation error found in a prompt template."""

    pattern: str
    reason: str


def validate_prompt_template(text: str) -> list[PromptTemplateError]:
    """
    Validate a user-authored prompt template text against PROMPT_SAFE_TOKENS.

    Why this exists:
    - prompt fields submitted via the control-plane API are stored before the
      agent ever executes; without up-front validation a bad template silently
      breaks the agent on the first chat message

    How to use:
    - call before persisting any field whose FieldSpec.type == "prompt"
    - an empty return list means the template is safe to store
    - a non-empty list means the create/update should be rejected with 422

    Validation rule:
    - any {simple_identifier} not in PROMPT_SAFE_TOKENS is an error
    - non-simple brace patterns ({}, {0}, {toto.toto}, { x }) are not matched
      and are silently preserved as literals by the renderer — no error raised,
      because they cannot be confused with template tokens (they will never be
      substituted and they no longer crash the renderer)

    Example:
    - validate_prompt_template("Today is {today}.")  →  []
    - validate_prompt_template("Hello {name}!")      →  [PromptTemplateError(...)]
    """
    errors: list[PromptTemplateError] = []
    seen: set[str] = set()

    for match in _SIMPLE_TOKEN_RE.finditer(text):
        token = match.group(1)
        raw = match.group(0)
        if token not in PROMPT_SAFE_TOKENS and raw not in seen:
            seen.add(raw)
            errors.append(
                PromptTemplateError(
                    pattern=raw,
                    reason=(
                        f"Unknown template token. "
                        f"Supported tokens are: {_SUPPORTED_HINT}."
                    ),
                )
            )

    return errors
