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
