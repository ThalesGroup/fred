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
Canonical prompt-template token registry.

Why this module exists:
- define the single source of truth for which {tokens} are substituted in
  user-authored system prompts
- let the renderer in fred-runtime import that token set, so the registry and
  the substitution stay in sync automatically

Why there is no validator here (#2277):
- the renderer substitutes a token only when it is present in this registry and
  otherwise leaves the matched text verbatim, so an unrecognized `{token}` is
  already harmless — it renders as itself and cannot crash the agent
- rejecting unknown tokens at save time was therefore a false positive: it
  blocked prompts such as `Hello {name}` that would have rendered correctly,
  with no in-product documentation or UI hint to warn the author
- the accepted trade-off is that a typo (`{todya}`) now reaches the prompt as
  literal text instead of being caught on write; that failure is visible to the
  author in the agent's output

How to use:
- import PROMPT_SAFE_TOKENS to get the canonical {token} → description map
"""

from __future__ import annotations

from typing import Final

# Canonical set of runtime tokens available in user-authored system prompts.
# Key   = token name (used inside {…} in the prompt text).
# Value = human-readable description, intended for a prompt-editor UI hint.
#
# To add a new supported token: add one entry here plus its runtime value in
# `safe_prompt_token_map` (fred-runtime) — no other site needs to change.
PROMPT_SAFE_TOKENS: Final[dict[str, str]] = {
    "today": "ISO-8601 date at execution time (e.g. 2026-05-07)",
    "response_language": "Human-readable response language (e.g. English, français)",
    "session_id": "Active session identifier",
    "user_id": "Authenticated user identifier",
    "agent_id": "Agent definition identifier",
}
