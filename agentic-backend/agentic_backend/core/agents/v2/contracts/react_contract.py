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
Fred-facing ReAct contract types.

Why this module exists:
- keep the agent/runtime message contract separate from LangChain message types
- make the ReAct input/output surface readable without digging through executor code

How to use:
- import these models when you need to validate, store, or inspect v2 ReAct chat state
- keep LangChain-specific conversions in adapter modules, not here

Example:
- `ReActInput(messages=(ReActMessage(role=ReActMessageRole.USER, content="hello"),))`
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenModel(BaseModel):
    """Shared frozen pydantic base for v2 ReAct contract models."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class ReActMessageRole(str, Enum):
    """
    Stable Fred-side roles for one ReAct transcript message.

    Why this exists:
    - Fred stores and transports ReAct chat state independently from LangChain classes
    - one small enum keeps the transcript shape explicit and typed

    How to use:
    - assign the role when creating one `ReActMessage`

    Example:
    - `ReActMessageRole.USER`
    """

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ReActToolCall(FrozenModel):
    """
    Stable Fred-side representation of one assistant tool call.

    Why this exists:
    - the runtime needs a transport-friendly tool-call model that is not tied to one SDK
    - tests and persistence should inspect tool calls without LangChain internals

    How to use:
    - attach it to one assistant `ReActMessage`

    Example:
    - `ReActToolCall(call_id="call-1", name="ls", arguments={"path": "/corpus"})`
    """

    call_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)


class ReActMessage(FrozenModel):
    """
    One Fred-side ReAct transcript message.

    Why this exists:
    - the v2 runtime needs one typed transcript format that remains stable across
      execution backends
    - validation here keeps invalid tool-call/tool-result shapes out of runtime code

    How to use:
    - build user, assistant, system, or tool messages for one `ReActInput`

    Example:
    - `ReActMessage(role=ReActMessageRole.USER, content="show /corpus")`
    """

    role: ReActMessageRole
    content: str = Field(..., min_length=0)
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_calls: tuple[ReActToolCall, ...] = ()

    @model_validator(mode="after")
    def validate_message_shape(self) -> "ReActMessage":
        """
        Enforce the small invariants of the Fred-side transcript shape.

        Why this exists:
        - assistant tool calls and tool-result linkage should fail early at model validation
        - runtime code should not repeat these structural checks every turn

        How to use:
        - instantiate `ReActMessage`; validation runs automatically

        Example:
        - `ReActMessage(role=ReActMessageRole.TOOL, content="ok", tool_call_id="call-1")`
        """

        if self.tool_calls and self.role != ReActMessageRole.ASSISTANT:
            raise ValueError("Only assistant messages may declare tool_calls.")
        if self.tool_call_id is not None and self.role != ReActMessageRole.TOOL:
            raise ValueError("Only tool messages may declare tool_call_id.")
        return self


class ReActInput(FrozenModel):
    """
    Typed chat input accepted by the v2 ReAct runtime.

    Why this exists:
    - runtime entrypoints should validate the minimum transcript contract once
    - callers should not pass empty or tool-only transcripts into the executor

    How to use:
    - build one or more `ReActMessage` values and wrap them in `ReActInput`

    Example:
    - `ReActInput(messages=(ReActMessage(role=ReActMessageRole.USER, content="hello"),))`
    """

    messages: tuple[ReActMessage, ...]

    @model_validator(mode="after")
    def validate_messages(self) -> "ReActInput":
        """
        Ensure one ReAct input contains at least one user message.

        Why this exists:
        - the runtime expects a real user turn, not an empty transcript shell
        - validating here keeps executor code focused on execution

        How to use:
        - instantiate `ReActInput`; validation runs automatically

        Example:
        - `ReActInput(messages=(ReActMessage(role=ReActMessageRole.USER, content="hello"),))`
        """

        if not self.messages:
            raise ValueError("ReActInput.messages must contain at least one message.")
        if not any(message.role == ReActMessageRole.USER for message in self.messages):
            raise ValueError(
                "ReActInput.messages must contain at least one user message."
            )
        return self


class ReActOutput(FrozenModel):
    """
    Stable Fred-side ReAct execution result.

    Why this exists:
    - callers need the final assistant message and the normalized transcript in one object
    - this keeps LangChain result objects out of agent-facing code

    How to use:
    - consume it from `Executor.invoke(...)`

    Example:
    - `output.final_message.content`
    """

    final_message: ReActMessage
    transcript: tuple[ReActMessage, ...]
