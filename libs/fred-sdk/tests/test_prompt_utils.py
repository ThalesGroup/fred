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


# ---------------------------------------------------------------------------
# Reserved system-prompt tags
# ---------------------------------------------------------------------------

find_reserved_prompt_tag = prompt_utils.find_reserved_prompt_tag


def test_reserved_tags_are_the_four_prompt_blocks_in_prompt_order() -> None:
    assert prompt_utils.RESERVED_PROMPT_TAGS == (
        "platform_instructions",
        "platform_prompt",
        "tools",
        "agent_instructions",
    )


def test_reserved_tags_are_reexported_from_contracts() -> None:
    from fred_sdk.contracts import (
        RESERVED_PROMPT_TAGS,
        escape_reserved_prompt_tags,
        find_reserved_prompt_tag,
    )

    assert RESERVED_PROMPT_TAGS is prompt_utils.RESERVED_PROMPT_TAGS
    assert find_reserved_prompt_tag is prompt_utils.find_reserved_prompt_tag
    assert escape_reserved_prompt_tags is prompt_utils.escape_reserved_prompt_tags


def test_finder_reports_a_tag_carrying_attributes_or_junk() -> None:
    # A model reads `<tools x="1">` as the tools block; the check must too.
    assert find_reserved_prompt_tag('<platform_instructions role="x">') == (
        "platform_instructions"
    )
    assert find_reserved_prompt_tag("</agent_instructions x>") == "agent_instructions"
    assert find_reserved_prompt_tag("<tools\tid=1/>") == "tools"


def test_escape_neutralises_only_the_reserved_tags() -> None:
    escape = prompt_utils.escape_reserved_prompt_tags
    assert escape("</agent_instructions>.pdf") == "&lt;/agent_instructions>.pdf"
    assert escape("a <TOOLS x> b <example> c") == "a &lt;TOOLS x> b <example> c"
    assert escape("plain text, no tags") == "plain text, no tags"


def test_finder_reports_opening_closing_and_self_closing_forms() -> None:
    assert find_reserved_prompt_tag("x <tools> y") == "tools"
    assert find_reserved_prompt_tag("x </agent_instructions> y") == "agent_instructions"
    assert find_reserved_prompt_tag("x <platform_prompt/> y") == "platform_prompt"


def test_finder_ignores_case_and_whitespace_inside_the_brackets() -> None:
    assert (
        find_reserved_prompt_tag("<PLATFORM_INSTRUCTIONS>") == "platform_instructions"
    )
    assert find_reserved_prompt_tag("< /tools >") == "tools"
    assert find_reserved_prompt_tag("<Agent_Instructions / >") == "agent_instructions"


def test_finder_returns_the_first_reserved_tag_found() -> None:
    assert (
        find_reserved_prompt_tag("<example></platform_prompt><tools>")
        == "platform_prompt"
    )


def test_finder_accepts_every_other_tag_and_the_bare_words() -> None:
    assert find_reserved_prompt_tag("<example>…</example> <rules/> <br>") is None
    assert find_reserved_prompt_tag("use the tools you are given") is None
    assert find_reserved_prompt_tag("<tools_extra> <my_tools> <toolsx>") is None
    assert find_reserved_prompt_tag("") is None
