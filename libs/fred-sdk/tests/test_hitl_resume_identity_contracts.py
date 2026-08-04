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

`checkpoint_id` and `interrupt_id` are two distinct fields on
`HumanInputRequest` and `ExecutionConfig`, never aliases for each other:
- `checkpoint_id`: a real checkpointer-storage identifier, populated only
  by the legacy Graph V2 runtime.
- `interrupt_id`: LangGraph's own `Interrupt.id`, populated only by the
  ReAct V2 runtime.

These tests pin that independence at the contract level.
"""

from __future__ import annotations

from fred_sdk.contracts.runtime import ExecutionConfig, HumanInputRequest


def test_human_input_request_checkpoint_id_and_interrupt_id_default_to_none() -> None:
    request = HumanInputRequest(question="Proceed?")
    assert request.checkpoint_id is None
    assert request.interrupt_id is None


def test_human_input_request_checkpoint_id_and_interrupt_id_are_independent() -> None:
    request = HumanInputRequest(
        question="Proceed?", checkpoint_id="cp-1", interrupt_id="interrupt-a"
    )
    assert request.checkpoint_id == "cp-1"
    assert request.interrupt_id == "interrupt-a"
    assert request.checkpoint_id != request.interrupt_id

    interrupt_only = request.model_copy(update={"checkpoint_id": None})
    assert interrupt_only.checkpoint_id is None
    assert interrupt_only.interrupt_id == "interrupt-a"


def test_execution_config_checkpoint_id_and_interrupt_id_are_independent() -> None:
    config = ExecutionConfig(
        session_id="s1", checkpoint_id="cp-1", interrupt_id="interrupt-a"
    )
    assert config.checkpoint_id == "cp-1"
    assert config.interrupt_id == "interrupt-a"

    resume_only = ExecutionConfig(
        session_id="s1", interrupt_id="interrupt-a", resume_payload={"choice_id": "ok"}
    )
    assert resume_only.checkpoint_id is None
    assert resume_only.interrupt_id == "interrupt-a"
