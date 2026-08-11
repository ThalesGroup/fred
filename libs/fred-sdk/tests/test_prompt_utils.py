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
Tests for fred_sdk.contracts.prompt_utils.

The module is now a pure registry: save-time validation of unknown {tokens}
was removed in #2277 because the fred-runtime renderer already preserves any
token outside PROMPT_SAFE_TOKENS verbatim, making rejection a false positive.

These tests pin the registry itself — its exact key set is a contract shared
with `safe_prompt_token_map` in fred-runtime, and adding a key here without
adding the matching runtime value would render that token as empty text.
"""

import fred_sdk.contracts.prompt_utils as prompt_utils
from fred_sdk.contracts import PROMPT_SAFE_TOKENS as PROMPT_SAFE_TOKENS_REEXPORT

PROMPT_SAFE_TOKENS = prompt_utils.PROMPT_SAFE_TOKENS

# ---------------------------------------------------------------------------
# PROMPT_SAFE_TOKENS registry
# ---------------------------------------------------------------------------


def test_safe_tokens_contains_expected_keys() -> None:
    assert set(PROMPT_SAFE_TOKENS.keys()) == {
        "today",
        "response_language",
        "session_id",
        "user_id",
        "agent_id",
    }


def test_safe_tokens_all_have_non_empty_descriptions() -> None:
    for key, desc in PROMPT_SAFE_TOKENS.items():
        assert desc, f"Token '{key}' has an empty description"


def test_safe_tokens_are_simple_identifiers() -> None:
    """
    Every registry key must be a bare identifier.

    The renderer matches `\\{([a-zA-Z_][a-zA-Z0-9_]*)\\}`; a key that does not
    fit that shape could never be substituted and would silently do nothing.
    """
    for key in PROMPT_SAFE_TOKENS:
        assert key.isidentifier(), f"Token '{key}' is not a simple identifier"


def test_registry_is_re_exported_from_contracts_package() -> None:
    assert PROMPT_SAFE_TOKENS_REEXPORT is PROMPT_SAFE_TOKENS


# ---------------------------------------------------------------------------
# Removed surface (#2277)
# ---------------------------------------------------------------------------


def test_validator_surface_is_gone() -> None:
    """
    The validator must not come back without a deliberate decision.

    Re-adding save-time rejection would once again block prompts such as
    `Hello {name}` that the renderer handles correctly.
    """
    assert not hasattr(prompt_utils, "validate_prompt_template")
    assert not hasattr(prompt_utils, "PromptTemplateError")
