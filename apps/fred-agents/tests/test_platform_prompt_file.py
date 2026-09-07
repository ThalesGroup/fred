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
`config/platform_prompt.json` — the two blocks that open every agent's system
prompt on this pod.

These tests live here, next to the file, rather than in fred-runtime: the
runtime only knows how to *load and compose* whatever a pod ships, and pinning
the wording there would test a fixture instead of the deployment. What is
asserted below is the real shipped text.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fred_runtime.app._catalogs import PlatformPromptFile, load_platform_prompt_file
from pydantic import ValidationError

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "platform_prompt.json"


@pytest.fixture(scope="module")
def shipped() -> PlatformPromptFile:
    return load_platform_prompt_file(CONFIG_PATH)


def test_the_shipped_file_parses_and_carries_both_blocks(
    shipped: PlatformPromptFile,
) -> None:
    # A pod with no file starts with neither head block, so a file that fails to
    # parse must fail here rather than at boot in a built image.
    assert shipped.platform_prompt.strip() != ""
    assert shipped.platform_instructions.strip() != ""


def test_a_missing_block_is_rejected_rather_than_defaulted() -> None:
    # Both fields are required on purpose: an optional one would let a bad edit
    # drop a block silently, since the composer renders nothing for an empty one.
    with pytest.raises(ValidationError):
        PlatformPromptFile.model_validate(
            {"version": 1, "platform_prompt": "hello"},
        )


def test_a_typoed_key_is_rejected_rather_than_ignored() -> None:
    with pytest.raises(ValidationError):
        PlatformPromptFile.model_validate(
            {
                "version": 1,
                "platform_prompt": "hello",
                "platform_instructions": "rules",
                "platfrom_prompt": "typo",
            },
        )


def test_instructions_keep_the_tool_failure_recovery_rule(
    shipped: PlatformPromptFile,
) -> None:
    # Regression for #2073, re-homed 2026-08-31: some capability tools catch
    # their own exceptions and return a troubleshooting message as an ordinary
    # tool result. Without this guidance the model has surfaced that raw text as
    # its final answer instead of retrying or falling back to context already
    # gathered. The rule moved out of `build_tool_failure_recovery_suffix` into
    # these shipped instructions; this test follows it there so the behaviour
    # stays pinned rather than silently lost in the move.
    #
    # The markdown is hard-wrapped; the model reads the text, not the wrapping,
    # so assert against the unwrapped form rather than pinning line breaks.
    flat = " ".join(shipped.platform_instructions.split())

    assert "never present that raw text as your final answer" in flat
    assert "retry with corrected arguments" in flat
    assert "answer from what other calls already returned" in flat


def test_instructions_tell_the_model_to_actually_use_its_tools(
    shipped: PlatformPromptFile,
) -> None:
    # The reason this block exists at all, and the reason it is the read-only
    # one: an admin can rewrite the platform prompt above it freely, and
    # tool-usage discipline must not be rewritable along with it.
    flat = " ".join(shipped.platform_instructions.split())

    assert "Never invent a tool name" in flat
    assert "call it instead of answering from memory" in flat


def test_the_default_prompt_is_a_usable_starting_point(
    shipped: PlatformPromptFile,
) -> None:
    # A deployment that never opens the admin page runs on this text, so it has
    # to be an answerable prompt rather than a placeholder telling an operator
    # to replace it.
    flat = " ".join(shipped.platform_prompt.split())

    assert "assistant of the Fred platform" in flat
    assert "in the language the user wrote in" in flat
    assert "rather than guessing" in flat
