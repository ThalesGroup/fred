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
Graph runtime contracts needed by the public authoring surface.

Why this module exists:
- authoring helpers need types like GraphNodeContext and GraphNodeResult without
  importing runtime implementations
- keeping these contracts here preserves a clean SDK dependency graph
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol

from fred_core.store import VectorSearchHit
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ConfigDict, Field

from ..contracts.context import (
    AgentInvocationResult,
    ArtifactScope,
    BoundRuntimeContext,
    ConversationTurn,
    FetchedResource,
    PublishedArtifact,
    ResourceScope,
    ToolInvocationResult,
    UiPart,
)
from ..contracts.models import TuningValue
from ..contracts.runtime import (
    HumanInputRequest,
    RuntimeServices,
    ThoughtKind,
    ThoughtRecord,
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class GraphExecutionOutput(FrozenModel):
    """Final user-facing outcome of a graph run."""

    content: str = ""
    sources: tuple[VectorSearchHit, ...] = ()
    ui_parts: tuple[UiPart, ...] = ()
    thought_trace: tuple[ThoughtRecord, ...] = ()
    token_usage: dict[str, int] | None = None


class GraphNodeResult(FrozenModel):
    """Result of one business step in the graph."""

    state_update: dict[str, object] = Field(default_factory=dict)
    route_key: str | None = None


class ThoughtWriter(Protocol):
    """
    Handle for streaming reasoning text into an open thought block.

    Obtained from `async with context.thinking(...) as thought:`.
    Both methods are fire-and-forget from the author's perspective — the
    runtime handles buffering, event emission, and timing.
    """

    async def write(self, text: str) -> None:
        """Emit one THOUGHT_DELTA fragment into the current block."""
        ...

    async def conclude(self, text: str) -> None:
        """Set the one-line conclusion text that will appear in THOUGHT_END."""
        ...


class GraphNodeContext(Protocol):
    """
    Runtime capabilities available inside one node handler.

    Node handlers should stay business-focused: read state, call these methods,
    return `GraphNodeResult`. Orchestration and persistence are handled by the
    runtime executor.
    """

    @property
    def binding(self) -> BoundRuntimeContext:
        raise NotImplementedError()

    @property
    def services(self) -> RuntimeServices:
        raise NotImplementedError()

    @property
    def model(self) -> BaseChatModel | None:
        raise NotImplementedError()

    @property
    def tuning_values(self) -> dict[str, TuningValue]:
        """
        Admin-set tuning field values for the current managed agent instance.

        Why this exists:
        - graph steps need to read values stored by the team admin at enrollment
          time (system prompt, planning instructions, feature flags, thresholds)
          without reaching into runtime internals

        How to use it:
        - call inside any node handler to read a specific field value
        - always provide a typed default so the step degrades gracefully when
          the admin left the field blank

        Example:
        ```python
        system_prompt = context.tuning_values.get("prompts.system", "")
        verbose = context.tuning_values.get("settings.verbose", False)
        delay_ms = int(context.tuning_values.get("settings.delay_ms", 0))
        ```
        """
        raise NotImplementedError()

    def emit_status(
        self,
        status: str,
        detail: str | None = None,
    ) -> None:
        """
        Publish a short operational progress signal for the current graph step.

        Use this for generic "what am I doing right now" signals (loading,
        routing, finalising). For structured chain-of-thought reasoning, use
        `context.thinking()` or `context.emit_thought()` instead.

        Example:
        ```python
        context.emit_status("load_context", "Fetching 3 documents.")
        context.emit_status("routing", "Selecting downstream agent.")
        ```
        """
        raise NotImplementedError()

    def thinking(
        self,
        phase: ThoughtKind,
        *,
        title: str | None = None,
    ) -> AbstractAsyncContextManager[ThoughtWriter]:
        """
        Open a structured reasoning block and stream text into it.

        Emits THOUGHT_START on entry, one THOUGHT_DELTA per `thought.write()`
        call, and THOUGHT_END on exit (even if the block body raised). The
        runtime measures wall-clock duration automatically.

        Works on any model family, including Mistral. On models with native
        extended thinking (Claude 3.7+) the runtime also emits THOUGHT_* events
        from native thinking tokens, which appear as separate blocks.

        Example:
        ```python
        async with context.thinking("planning", title="Deciding which tools to call") as thought:
            await thought.write("The user is asking about X.")
            await thought.write("Relevant tools: knowledge_search, sql_query.")
            await thought.conclude("Will call knowledge_search first.")
        ```
        """
        raise NotImplementedError()

    def emit_thought(
        self,
        phase: ThoughtKind,
        text: str,
        *,
        title: str | None = None,
        conclusion: str | None = None,
    ) -> None:
        """
        Emit a complete reasoning block synchronously in one call.

        Convenience wrapper around `thinking()` for cases where the full
        reasoning text is known upfront and streaming granularity is not needed.
        Emits THOUGHT_START + THOUGHT_DELTA + THOUGHT_END in sequence.

        Example:
        ```python
        context.emit_thought(
            "observation",
            "Found 3 documents. Top score 0.97. Query matched closely.",
            title="Knowledge search result",
        )
        ```
        """
        raise NotImplementedError()

    def emit_assistant_delta(self, delta: str) -> None:
        raise NotImplementedError()

    async def invoke_model(
        self,
        messages: list[BaseMessage],
        *,
        operation: str = "default",
    ) -> BaseMessage:
        raise NotImplementedError()

    async def invoke_structured_model(
        self,
        output_model: type[BaseModel],
        messages: list[BaseMessage],
        *,
        operation: str = "default",
    ) -> BaseModel:
        raise NotImplementedError()

    async def invoke_tool(
        self, tool_ref: str, payload: dict[str, object]
    ) -> ToolInvocationResult:
        raise NotImplementedError()

    async def invoke_runtime_tool(
        self, tool_name: str, arguments: dict[str, object]
    ) -> object:
        raise NotImplementedError()

    async def invoke_agent(
        self,
        agent_id: str,
        message: str,
        *,
        prior_turns: tuple[ConversationTurn, ...] = (),
    ) -> AgentInvocationResult:
        raise NotImplementedError()

    async def publish_text(
        self,
        *,
        file_name: str,
        text: str,
        key: str | None = None,
        title: str | None = None,
        content_type: str = "text/plain; charset=utf-8",
        scope: ArtifactScope = ArtifactScope.USER,
        target_user_id: str | None = None,
    ) -> PublishedArtifact:
        """
        Publish a text artifact to the runtime artifact store.

        Why this exists:
        - graph nodes often need to emit files (reports, SQL, summaries)
        - authors should not have to reach into storage adapters directly

        How to use it:
        - pass a file name and text payload
        - optionally scope it to a user/team and set a stable key

        Example:
        - `artifact = await context.publish_text(file_name="result.txt", text=sql)`
        """
        raise NotImplementedError()

    async def publish_bytes(
        self,
        *,
        file_name: str,
        content_bytes: bytes,
        key: str | None = None,
        title: str | None = None,
        content_type: str | None = None,
        scope: ArtifactScope = ArtifactScope.USER,
        target_user_id: str | None = None,
    ) -> PublishedArtifact:
        """
        Publish a binary artifact to the runtime artifact store.

        Why this exists:
        - graph nodes may generate PDFs, images, or other binary outputs
        - the runtime owns storage concerns, not the authoring layer

        How to use it:
        - pass raw bytes plus a file name and optional content type

        Example:
        - `artifact = await context.publish_bytes(file_name="chart.png", content_bytes=png)`
        """
        raise NotImplementedError()

    async def fetch_resource(
        self,
        *,
        key: str,
        scope: ResourceScope = ResourceScope.AGENT_CONFIG,
        target_user_id: str | None = None,
    ) -> FetchedResource:
        """
        Fetch a binary resource from the runtime resource store.

        Why this exists:
        - graph nodes often reuse packaged files or configuration assets
        - this keeps resource access consistent with runtime policies

        How to use it:
        - pass the resource key and optional scope

        Example:
        - `resource = await context.fetch_resource(key="prompts/system.md")`
        """
        raise NotImplementedError()

    async def fetch_text_resource(
        self,
        *,
        key: str,
        scope: ResourceScope = ResourceScope.AGENT_CONFIG,
        target_user_id: str | None = None,
        encoding: str = "utf-8",
    ) -> str:
        """
        Fetch a text resource from the runtime resource store.

        Why this exists:
        - authors frequently need prompt templates or static text resources
        - the runtime should handle decoding and access rules

        How to use it:
        - pass the resource key and optional encoding

        Example:
        - `prompt = await context.fetch_text_resource(key="prompts/system.md")`
        """
        raise NotImplementedError()

    async def request_human_input(self, request: HumanInputRequest) -> object:
        raise NotImplementedError()


__all__ = [
    "AgentInvocationResult",
    "GraphExecutionOutput",
    "GraphNodeContext",
    "GraphNodeResult",
    "ThoughtRecord",
    "ThoughtWriter",
]
