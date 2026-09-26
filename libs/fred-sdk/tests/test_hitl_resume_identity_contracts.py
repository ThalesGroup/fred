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
Offline unit tests for the HITL resume identity contract (#2216 P1).

`interrupt_id` and `occurrence_id` are distinct fields, never aliases:
- `interrupt_id`: LangGraph's own `Interrupt.id` (ReAct and Graph agents).
- `occurrence_id`: one pause within an interrupt, derived from a tool call
  when the pause originates there.

These tests pin that independence at the contract level.
"""

from __future__ import annotations

import pytest
from fred_sdk.contracts.runtime import ExecutionConfig, HumanInputRequest
from pydantic import ValidationError


def test_human_input_request_resume_identity_defaults_to_none() -> None:
    request = HumanInputRequest(question="Proceed?")
    assert request.interrupt_id is None
    assert request.occurrence_id is None
    assert "occurrence_id" not in request.model_dump(mode="json")


def test_checkpoint_id_is_no_longer_part_of_the_pause_or_the_run() -> None:
    with pytest.raises(ValidationError, match="checkpoint_id"):
        HumanInputRequest.model_validate(
            {"question": "Proceed?", "checkpoint_id": "cp-1"}
        )
    with pytest.raises(ValidationError, match="checkpoint_id"):
        ExecutionConfig.model_validate({"session_id": "s1", "checkpoint_id": "cp-1"})


def test_human_input_request_occurrence_id_names_a_pause_within_interrupt() -> None:
    request = HumanInputRequest(
        question="Choose one",
        interrupt_id="interrupt-a",
        occurrence_id="tool-call-2",
    )

    assert request.interrupt_id == "interrupt-a"
    assert request.occurrence_id == "tool-call-2"


def test_execution_config_carries_the_resumed_interrupt() -> None:
    resume = ExecutionConfig(
        session_id="s1", interrupt_id="interrupt-a", resume_payload={"choice_id": "ok"}
    )
    assert resume.interrupt_id == "interrupt-a"
