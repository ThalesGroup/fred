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
Offline unit tests for `react_message_codec.graph_input_from_react_input`'s
HITL resume targeting (#2216 P1).

Why this file exists:
- proves the codec builds LangGraph's targeted map-form
  `Command(resume={interrupt_id: payload})` whenever `interrupt_id` is set
- proves a ReAct V2 resume WITHOUT `interrupt_id` fails closed — there is
  no scalar `Command(resume=payload)` fallback, because a scalar resume
  gives LangGraph no identity to match against at all
- proves a normal (non-resume) turn is unaffected and never even looks at
  `interrupt_id`/`checkpoint_id`
"""

from __future__ import annotations

import pytest
from fred_runtime.react.react_message_codec import graph_input_from_react_input
from fred_sdk.contracts.react_contract import ReActInput, ReActMessage, ReActMessageRole
from fred_sdk.contracts.runtime import ExecutionConfig
from langgraph.types import Command


def _sanitize(name: str) -> str:
    return name


def test_resume_with_interrupt_id_uses_targeted_map_form() -> None:
    config = ExecutionConfig(
        session_id="s1",
        interrupt_id="interrupt-a",
        resume_payload={"choice_id": "proceed"},
    )

    result = graph_input_from_react_input(
        ReActInput.model_construct(messages=()),
        config,
        sanitize_tool_name=_sanitize,
    )

    assert isinstance(result, Command)
    assert result.resume == {"interrupt-a": {"choice_id": "proceed"}}


def test_resume_without_interrupt_id_fails_closed() -> None:
    # A ReAct V2 resume always goes through the HTTP gate
    # (`agent_app._validate_session_checkpoint_access`), which never
    # forwards a resume without a validated interrupt_id. A caller that
    # somehow reaches this codec without one must not silently fall back to
    # an unscoped scalar resume — it must fail loudly instead.
    config = ExecutionConfig(
        session_id="s1",
        resume_payload={"choice_id": "proceed"},
    )

    with pytest.raises(RuntimeError, match="interrupt_id"):
        graph_input_from_react_input(
            ReActInput.model_construct(messages=()),
            config,
            sanitize_tool_name=_sanitize,
        )


def test_resume_with_only_checkpoint_id_still_fails_closed() -> None:
    # checkpoint_id is the legacy Graph V2 field — this codec is exclusively
    # used by the ReAct V2 runtime, so a checkpoint_id with no interrupt_id
    # must not be treated as an acceptable substitute.
    config = ExecutionConfig(
        session_id="s1",
        checkpoint_id="cp-1",
        resume_payload={"choice_id": "proceed"},
    )

    with pytest.raises(RuntimeError, match="interrupt_id"):
        graph_input_from_react_input(
            ReActInput.model_construct(messages=()),
            config,
            sanitize_tool_name=_sanitize,
        )


def test_fresh_turn_ignores_interrupt_id_and_builds_message_payload() -> None:
    # interrupt_id may still be set (e.g. propagated for tracing) on a
    # normal turn — only `resume_payload` decides which branch runs.
    config = ExecutionConfig(session_id="s1", interrupt_id="stale-from-a-prior-turn")
    input_model = ReActInput(
        messages=(ReActMessage(role=ReActMessageRole.USER, content="hi"),)
    )

    result = graph_input_from_react_input(
        input_model, config, sanitize_tool_name=_sanitize
    )

    assert isinstance(result, dict)
    messages = result["messages"]
    assert isinstance(messages, list)
    assert len(messages) == 1
