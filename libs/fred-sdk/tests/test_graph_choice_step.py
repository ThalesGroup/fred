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

from __future__ import annotations

import asyncio
from typing import cast

from fred_sdk.contracts.runtime import HumanChoiceOption
from fred_sdk.graph import GraphNodeContext
from fred_sdk.graph.authoring.api import choice_step


class _ChoiceContext:
    """
    Tiny fake graph context that returns one scripted human response.

    Why this exists:
    - `choice_step(...)` only needs `request_human_input(...)` for this
      regression, so a tiny test double keeps the test fully offline

    How to use it:
    - create one instance per test with the desired resume payload

    Example:
    - `_ChoiceContext({"choice_id": "confirm"})`
    """

    def __init__(self, response: object) -> None:
        self._response = response

    async def request_human_input(self, request):  # type: ignore[no-untyped-def]
        return self._response


def test_choice_step_reads_structured_resume_payload() -> None:
    """Verify `choice_step(...)` returns the selected id from a dict payload.

    Why: Graph HITL resumes now use `{"choice_id": ...}` as the primary shape.
    How: Resume with a dict and compare the normalized return value.

    Example:
    - `pytest tests/test_graph_choice_step.py -q`
    """

    result = asyncio.run(
        choice_step(
            cast(GraphNodeContext, _ChoiceContext({"choice_id": "confirm"})),
            stage="transfer_confirmation",
            title="Confirm Transfer",
            question="Proceed?",
            choices=(HumanChoiceOption(id="confirm", label="Confirm"),),
        )
    )

    assert result == "confirm"


def test_choice_step_keeps_backward_compatibility_with_string_resume() -> None:
    """Verify `choice_step(...)` still accepts a bare string resume payload.

    Why: Existing callers may still resume older graph pauses with plain strings.
    How: Resume with `"confirm"` and compare the normalized return value.

    Example:
    - `pytest tests/test_graph_choice_step.py -q`
    """

    result = asyncio.run(
        choice_step(
            cast(GraphNodeContext, _ChoiceContext("confirm")),
            stage="transfer_confirmation",
            title="Confirm Transfer",
            question="Proceed?",
            choices=(HumanChoiceOption(id="confirm", label="Confirm"),),
        )
    )

    assert result == "confirm"


def test_choice_step_response_preserves_comment() -> None:
    from fred_sdk.graph.authoring.api import choice_step_response

    result = asyncio.run(
        choice_step_response(
            cast(
                GraphNodeContext,
                _ChoiceContext({"choice_id": "confirm", "text": "Soon"}),
            ),
            stage="transfer_confirmation",
            title="Confirm Transfer",
            question="Proceed?",
            choices=(HumanChoiceOption(id="confirm", label="Confirm"),),
            free_text=True,
        )
    )

    assert result is not None
    assert result.choice_id == "confirm"
    assert result.text == "Soon"


def test_choice_step_response_accepts_skip_without_fabricating_choice() -> None:
    from fred_sdk.graph.authoring.api import choice_step_response

    result = asyncio.run(
        choice_step_response(
            cast(GraphNodeContext, _ChoiceContext({"skipped": True})),
            stage="scope_selection",
            title=None,
            question="Which scope?",
            choices=(HumanChoiceOption(id="a", label="A"),),
        )
    )

    assert result is not None
    assert result.skipped
    assert result.choice_id is None


def test_choice_step_keeps_legacy_free_text_carried_as_choice_id() -> None:
    result = asyncio.run(
        choice_step(
            cast(GraphNodeContext, _ChoiceContext({"choice_id": "A free-text reply"})),
            stage="test_free_text",
            title="Free text",
            question="Type a reply",
            choices=(HumanChoiceOption(id="__free_text__", label="Your reply"),),
        )
    )
    assert result == "A free-text reply"
