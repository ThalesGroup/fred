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

Ref: docs/backlog/BACKLOG.md §3d.9 (P1) — PROMPT_SAFE_TOKENS registry,
     validate_prompt_template (unknown tokens → error, non-simple braces preserved),
     crash-proof rendering for code braces and dotted-notation patterns.
"""

import pytest
from fred_sdk.contracts.prompt_utils import (
    PROMPT_SAFE_TOKENS,
    validate_prompt_template,
)

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


# ---------------------------------------------------------------------------
# Clean templates — no errors expected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "You are a helpful assistant.",
        "Today is {today}.",
        "Respond in {response_language}.",
        "Session: {session_id}, User: {user_id}, Agent: {agent_id}.",
        "All tokens: {today} {response_language} {session_id} {user_id} {agent_id}.",
        # Code braces are not simple identifiers — preserved as literals, no error
        "function main(workbook: ExcelScript.Workbook) { doSomething(); }",
        # Dotted notation is not a simple identifier — left as literal, no error
        "{toto.toto} should not be flagged",
        # Empty brace not a simple identifier
        "Use {} carefully",
        # Positional placeholder not a simple identifier
        "Value: {0}",
        # Whitespace inside braces not a simple identifier
        "{ not a token }",
    ],
)
def test_clean_templates(text: str) -> None:
    assert validate_prompt_template(text) == []


# ---------------------------------------------------------------------------
# Invalid templates — errors expected
# ---------------------------------------------------------------------------


def test_unknown_simple_token_single() -> None:
    errors = validate_prompt_template("Hello {name}!")
    assert len(errors) == 1
    assert errors[0].pattern == "{name}"
    assert "Unknown template token" in errors[0].reason
    # Error message must list the supported tokens
    for token in PROMPT_SAFE_TOKENS:
        assert token in errors[0].reason


def test_unknown_simple_token_multiple_distinct() -> None:
    errors = validate_prompt_template("{foo} and {bar} are unknown")
    patterns = {e.pattern for e in errors}
    assert patterns == {"{foo}", "{bar}"}


def test_unknown_simple_token_repeated_deduplicated() -> None:
    errors = validate_prompt_template("{foo} again {foo}")
    assert len(errors) == 1
    assert errors[0].pattern == "{foo}"


def test_mix_valid_and_invalid_tokens() -> None:
    errors = validate_prompt_template("Today is {today} and {bad_token} here.")
    assert len(errors) == 1
    assert errors[0].pattern == "{bad_token}"


def test_all_valid_tokens_produce_no_errors() -> None:
    text = " ".join(f"{{{k}}}" for k in PROMPT_SAFE_TOKENS)
    assert validate_prompt_template(text) == []


# ---------------------------------------------------------------------------
# Non-simple brace patterns are NOT flagged (renderer preserves them safely)
# ---------------------------------------------------------------------------


def test_dotted_notation_not_flagged() -> None:
    assert validate_prompt_template("{object.attr}") == []


def test_empty_braces_not_flagged() -> None:
    assert validate_prompt_template("{}") == []


def test_positional_placeholder_not_flagged() -> None:
    assert validate_prompt_template("{0}") == []


def test_whitespace_brace_not_flagged() -> None:
    assert validate_prompt_template("{ spaces }") == []


def test_code_block_not_flagged() -> None:
    prompt = (
        "You help users write Excel scripts. Example:\n"
        "function main(workbook: ExcelScript.Workbook) {\n"
        "    workbook.getActiveWorksheet().getCell(0, 0).setValue('Hello');\n"
        "}"
    )
    assert validate_prompt_template(prompt) == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_string_is_valid() -> None:
    assert validate_prompt_template("") == []


def test_no_braces_is_valid() -> None:
    assert validate_prompt_template("Plain text without any braces.") == []


def test_token_adjacent_to_punctuation() -> None:
    errors = validate_prompt_template("Hi, {unknown}!")
    assert len(errors) == 1
    assert errors[0].pattern == "{unknown}"


def test_known_token_at_start_and_end() -> None:
    assert validate_prompt_template("{today} is a great day, {user_id}.") == []
