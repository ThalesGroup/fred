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
Core authoring contract for Fred v2 agents.

This module matters because it defines the language an agent author uses to
describe a business role in Fred. The important question is not "how do I wire
LangGraph?" but "what kind of service am I building for a user?"

The v2 contract therefore separates the authoring surface from the execution
engine used later by the runtime. Authors describe the service in Fred terms;
the runtime then delegates execution to the appropriate implementation engine
such as the LangChain/LangGraph ReAct stack or the deep-agent runtime.

The main authoring families are:
- `ReActAgentDefinition` for assistants whose value comes from flexible
  conversation plus tools
- `DeepAgentDefinition` as a specialized ReAct authoring shape when the service
  still behaves like an assistant but needs a deeper planning/execution engine
- `GraphAgentDefinition` for services whose value comes from a clear business
  journey with explicit steps, decisions, and guarded actions

The models in this file are intentionally pure. They describe what the agent
is, what it needs, and what a developer or product owner should be able to
inspect safely before anything is executed.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Mapping
from enum import Enum
from typing import ClassVar, Dict, List, Literal, Optional, Protocol, TypeAlias, Union

from pydantic import AliasChoices, AnyUrl, BaseModel, ConfigDict, Field, model_validator

from .context import BoundRuntimeContext, ConversationTurn

# ---------------------------------------------------------------------------
# Agent tuning and MCP types — canonical SDK home.
# These were previously defined in core/agents/agent_spec.py.  That module
# now re-exports them from here so the rest of the monorepo keeps working.
# ---------------------------------------------------------------------------

FieldType = Literal[
    "string",
    "text",
    "text-multiline",
    "number",
    "integer",
    "boolean",
    "select",
    "array",
    "object",
    "prompt",
    "secret",
    "url",
]

# Scalar value that an admin can store for a FieldSpec field.
# Arrays and objects are composed from these scalars.
TuningScalar: TypeAlias = Union[str, int, float, bool]
TuningValue: TypeAlias = Union[
    TuningScalar, list[TuningScalar], dict[str, TuningScalar]
]


class UIHints(BaseModel):
    """UI hints for rendering the field in a user interface."""

    multiline: bool = False
    max_lines: int = 6
    placeholder: Optional[str] = None
    markdown: bool = False
    textarea: bool = False
    group: Optional[str] = None
    hide: bool = False


class FieldSpec(BaseModel):
    """Specification for a tunable field in an agent."""

    key: str
    type: FieldType
    title: str
    description: Optional[str] = None
    required: bool = False
    default: TuningValue | None = None
    enum: Optional[List[str]] = None
    min: Optional[float] = None
    max: Optional[float] = None
    pattern: Optional[str] = None
    item_type: Optional[FieldType] = None
    ui: UIHints = UIHints()


class ClientAuthMode(str, Enum):
    USER_TOKEN = "user_token"  # nosec B105
    NO_TOKEN = "no_token"  # nosec B105


class MCPServerConfiguration(BaseModel):
    """Configuration for an MCP server."""

    id: str
    name: str = Field(
        ..., description="react-i18next key for the name of the MCP server."
    )
    description: Optional[str] = Field(
        None, description="react-i18next key for the description of the MCP server."
    )
    transport: Optional[str] = Field(
        "sse",
        description=(
            "MCP server transport. Can be sse, stdio, websocket, streamable_http, "
            "or inprocess (local toolkit provider exposed in the MCP catalog)."
        ),
    )
    provider: Optional[str] = Field(
        None,
        description="Local provider key when transport=inprocess.",
    )
    url: Optional[str] = Field(None, description="URL and endpoint of the MCP server")
    sse_read_timeout: Optional[int] = Field(
        60 * 5,
        description="How long (in seconds) the client will wait for a new event before disconnecting",
    )
    command: Optional[str] = Field(
        None,
        description="Command to run for stdio transport.",
    )
    args: Optional[List[str]] = Field(
        None,
        description="Args to give the command as a list.",
    )
    env: Optional[Dict[str, str]] = Field(
        None, description="Environment variables to give the MCP server"
    )
    enabled: bool = Field(True, description="If false, this MCP server is ignored.")
    auth_mode: ClientAuthMode = Field(
        ClientAuthMode.USER_TOKEN, description="Client authentication mode."
    )
    config_fields: List[FieldSpec] = Field(
        default_factory=list,
        description=(
            "User-facing configuration options declared by this server. "
            "Rendered in the agent form beneath the server's activation checkbox. "
            "Values flow into RuntimeContext as tuning field values at execution time."
        ),
    )


class MCPServerRef(BaseModel):
    """
    Reference to an MCP server by logical id.

    Why this model exists:
    - agents should reference one logical MCP server by id rather than hard-code
      transport details such as URLs, commands, or environment variables
    - Fred resolves the concrete MCP configuration later for the current
      environment, tenant, and user

    How to use:
    - store the logical server id in `id`
    - for v2 agent profiles, prefer named constants exported from
      `fred_sdk.support.builtins` instead of repeating raw string ids

    Example:
    - `MCPServerRef(id="mcp-knowledge-flow-fs")`
    """

    id: str = Field(..., validation_alias=AliasChoices("id", "name"))
    require_tools: list[str] = []


class AgentTuning(BaseModel):
    """Runtime-editable tuning surface for one agent."""

    role: str = Field(..., description="The agent's mandatory role for discovery.")
    description: str = Field(
        ..., description="The agent's mandatory description for the UI."
    )
    tags: List[str] = Field(default_factory=list)
    fields: List[FieldSpec] = Field(default_factory=list)
    mcp_servers: list[MCPServerRef] = Field(default_factory=list)
    selected_mcp_server_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Admin-chosen subset of mcp_servers IDs to activate for this instance. "
            "Empty list means all declared servers are active."
        ),
    )
    values: dict[str, TuningValue] = Field(
        default_factory=dict,
        description="User-set field values keyed by FieldSpec.key, forwarded from control-plane.",
    )

    def dump(self) -> str:
        """Return a concise JSON summary for logging."""
        data = self.model_dump(exclude_defaults=True, mode="json")
        summary = {
            "description": data.get("description", self.description),
            "role": data.get("role", self.role),
            "tags": data.get("tags", []),
        }
        field_count = len(self.fields)
        if field_count > 0:
            summary["tunable_fields_count"] = field_count
        return json.dumps(summary, indent=2)


class AgentSettings(Protocol):
    """
    Minimal agent settings shape expected by authored-tool runtime helpers.

    Why this exists:
    - authored tools only need a few fields (id, name, team_id, tuning) and
      should not depend on a full backend settings model
    - using a Protocol keeps the SDK decoupled from backend persistence details

    How to use it:
    - pass any object with these attributes into authored-tool runtimes
    - backend implementations can satisfy this with their own settings model

    Example:
        >>> class Settings:
        ...     id = "agent-1"
        ...     name = "Example"
        ...     team_id = None
        ...     tuning = AgentTuning(role="r", description="d")
        >>> settings = Settings()
    """

    id: str
    name: str
    team_id: str | None
    tuning: "AgentTuning | None"


class FrozenModel(BaseModel):
    """Shared strict model base for the v2 agent contract."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class ExecutionCategory(str, Enum):
    """Top-level execution family used by runtime dispatch and inspection."""

    GRAPH = "graph"
    REACT = "react"
    DEEP = "deep"
    PROXY = "proxy"


class PreviewKind(str, Enum):
    """Safe preview rendering format shown to developers in inspection views."""

    NONE = "none"
    MERMAID = "mermaid"
    DAG = "dag"
    TEXT = "text"


class GraphNodeShape(str, Enum):
    """Visual hint for graph previews; does not affect runtime behavior."""

    RECT = "rect"
    ROUND = "round"
    DIAMOND = "diamond"


class ToolRefRequirement(FrozenModel):
    """
    Declares one Fred platform tool your agent can call.

    Use the constants from fred_sdk.support.builtins —
    do not write tool_ref strings by hand.

    Available constants:
        TOOL_REF_KNOWLEDGE_SEARCH          — search document libraries
        TOOL_REF_ARTIFACTS_PUBLISH_TEXT    — publish a markdown report
        TOOL_REF_RESOURCES_FETCH_TEXT      — read a config or template file
        TOOL_REF_LOGS_QUERY                — query backend logs
        TOOL_REF_TRACES_SUMMARIZE_CONVERSATION — summarise an execution trace

    The description field is what the model reads to decide when to call the
    tool — make it concrete and action-oriented.

    Example:
    ```python
    from fred_sdk.support.builtins import (
        TOOL_REF_KNOWLEDGE_SEARCH,
        TOOL_REF_ARTIFACTS_PUBLISH_TEXT,
    )

    declared_tool_refs = (
        ToolRefRequirement(
            tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
            description="Search the selected document libraries for relevant evidence.",
        ),
        ToolRefRequirement(
            tool_ref=TOOL_REF_ARTIFACTS_PUBLISH_TEXT,
            description="Publish the final report as a markdown artifact for the user.",
        ),
    )
    ```

    Note: `kind` and `required` are framework fields — leave them at their defaults.
    """

    kind: Literal["tool_ref"] = "tool_ref"
    required: bool = True
    description: str | None = None
    tool_ref: str = Field(..., min_length=1)


ToolRequirement: TypeAlias = ToolRefRequirement


class AgentPreview(FrozenModel):
    """Non-executable preview payload returned by inspection endpoints."""

    kind: PreviewKind
    content: str = ""
    note: str | None = None

    @classmethod
    def none(cls, *, note: str | None = None) -> "AgentPreview":
        return cls(kind=PreviewKind.NONE, content="", note=note)


class AgentInspection(FrozenModel):
    """
    Safe summary of an agent as a product capability.

    Inspection is meant to answer practical questions such as:
    - what role does this agent play?
    - what can it tune?
    - what tools or MCP services does it expect?
    - is it fundamentally a ReAct assistant or a workflow agent?
    """

    agent_id: str
    role: str
    description: str
    tags: tuple[str, ...] = ()
    fields: tuple[FieldSpec, ...] = ()
    execution_category: ExecutionCategory
    declared_tool_refs: tuple[ToolRequirement, ...] = Field(
        default=(),
        description=(
            "Exact Fred runtime tools declared by the agent author. "
            "This exists so inspection and UIs can explain what the agent expects "
            "before runtime binding happens."
        ),
    )
    default_mcp_servers: tuple[MCPServerRef, ...] = Field(
        default=(),
        description=(
            "Default MCP servers Fred should attach for this agent. "
            "These are runtime tool providers, not substitutes for first-class "
            "Fred declared tool refs."
        ),
    )
    preview: AgentPreview = Field(default_factory=AgentPreview.none)


class GraphNodeDefinition(FrozenModel):
    """One named business step in a graph authoring definition."""

    node_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str | None = None
    shape: GraphNodeShape = GraphNodeShape.RECT
    on_error: str | None = Field(
        default=None,
        description=(
            "Node to route to when this handler raises an unhandled exception. "
            "When set, the runtime catches the exception, writes 'node_error' "
            "into the graph state, emits a NodeErrorRuntimeEvent, and continues "
            "execution at the named node instead of crashing. "
            "Leave None to propagate the exception (existing behaviour)."
        ),
    )


class GraphEdgeDefinition(FrozenModel):
    """Unconditional transition from one graph node to another."""

    source: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    label: str | None = None


class GraphRouteDefinition(FrozenModel):
    """Named branch target emitted by conditional node handlers."""

    route_key: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    label: str | None = None


class GraphConditionalDefinition(FrozenModel):
    """Conditional routing table attached to one source node."""

    source: str = Field(..., min_length=1)
    routes: tuple[GraphRouteDefinition, ...]
    default_route_key: str | None = None

    @model_validator(mode="after")
    def validate_default_route(self) -> "GraphConditionalDefinition":
        route_keys = {route.route_key for route in self.routes}
        if (
            self.default_route_key is not None
            and self.default_route_key not in route_keys
        ):
            raise ValueError(
                f"default_route_key={self.default_route_key!r} is not declared in routes for source={self.source!r}"
            )
        return self


class GraphDefinition(FrozenModel):
    """
    Pure structure of a business journey.

    A graph definition is not the executable runtime. It is the shape of the
    service path the business wants to guarantee: where a request is routed,
    where context is gathered, where a human is asked to choose, and where an
    action may safely happen.

    Parallel groups:
    - `parallel_groups` declares sets of nodes that execute concurrently after
      a common fan-out node and converge before a common fan-in node
    - each group is a tuple of (fan_out_node, fan_in_node, member1, member2, ...)
    - the fan-out node must have no direct edge or conditional (the group
      replaces it); the fan-in node receives execution after all members finish
    - member nodes must not call invoke_model (no LLM streaming during parallel
      execution); tool calls and IO operations are safe
    """

    state_model_name: str = Field(..., min_length=1)
    entry_node: str = Field(..., min_length=1)
    nodes: tuple[GraphNodeDefinition, ...]
    edges: tuple[GraphEdgeDefinition, ...] = ()
    conditionals: tuple[GraphConditionalDefinition, ...] = ()
    parallel_groups: tuple[tuple[str, ...], ...] = Field(
        default=(),
        description=(
            "Each inner tuple declares one parallel fan-out/fan-in group as "
            "(fan_out_node, fan_in_node, member1, member2, ...). "
            "Member nodes run concurrently via asyncio.gather after fan_out "
            "and their state updates are merged before fan_in starts."
        ),
    )

    @model_validator(mode="after")
    def validate_topology(self) -> "GraphDefinition":
        node_ids = [node.node_id for node in self.nodes]
        unique_node_ids = set(node_ids)

        if len(unique_node_ids) != len(node_ids):
            raise ValueError(
                "GraphDefinition.nodes must contain unique node_id values."
            )

        if self.entry_node not in unique_node_ids:
            raise ValueError(
                f"GraphDefinition.entry_node={self.entry_node!r} is not declared in nodes."
            )

        for edge in self.edges:
            if edge.source not in unique_node_ids:
                raise ValueError(
                    f"Graph edge source={edge.source!r} is not declared in nodes."
                )
            if edge.target not in unique_node_ids:
                raise ValueError(
                    f"Graph edge target={edge.target!r} is not declared in nodes."
                )

        for conditional in self.conditionals:
            if conditional.source not in unique_node_ids:
                raise ValueError(
                    f"Graph conditional source={conditional.source!r} is not declared in nodes."
                )
            for route in conditional.routes:
                if route.target not in unique_node_ids:
                    raise ValueError(
                        f"Graph conditional target={route.target!r} is not declared in nodes."
                    )

        for group in self.parallel_groups:
            if len(group) < 4:
                raise ValueError(
                    "Each parallel_group must have at least 4 entries: "
                    "(fan_out_node, fan_in_node, member1, member2, ...)"
                )
            fan_out, fan_in = group[0], group[1]
            members = group[2:]
            for node in (fan_out, fan_in, *members):
                if node not in unique_node_ids:
                    raise ValueError(
                        f"Parallel group references unknown node {node!r}."
                    )
            if len(set(members)) != len(members):
                raise ValueError(
                    f"Parallel group for fan_out={fan_out!r} has duplicate member nodes."
                )
            if fan_out in members or fan_in in members:
                raise ValueError(
                    "fan_out and fan_in nodes must not appear as members in the same parallel group."
                )

        for node in self.nodes:
            if node.on_error is not None and node.on_error not in unique_node_ids:
                raise ValueError(
                    f"Node {node.node_id!r} declares on_error={node.on_error!r} "
                    "which is not declared in nodes."
                )

        return self

    def to_mermaid(self) -> str:
        """
        Render a safe, purely structural Mermaid preview.
        This does not compile or activate anything.
        """

        def sanitize_id(raw: str) -> str:
            text = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in raw)
            if not text:
                text = "node"
            if text[0].isdigit():
                text = f"n_{text}"
            reserved = {
                "class",
                "classdef",
                "click",
                "default",
                "end",
                "flowchart",
                "graph",
                "linkstyle",
                "style",
                "subgraph",
            }
            if text.lower() in reserved:
                text = f"node_{text}"
            return text

        id_map: dict[str, str] = {}
        used: set[str] = set()
        for node in self.nodes:
            base = sanitize_id(node.node_id)
            candidate = base
            suffix = 2
            while candidate in used:
                candidate = f"{base}_{suffix}"
                suffix += 1
            id_map[node.node_id] = candidate
            used.add(candidate)

        def node_line(node: GraphNodeDefinition) -> str:
            node_id = id_map[node.node_id]
            label = node.title.replace('"', '\\"')
            if node.shape == GraphNodeShape.ROUND:
                return f'  {node_id}(["{label}"]);'
            if node.shape == GraphNodeShape.DIAMOND:
                return f'  {node_id}{{"{label}"}};'
            return f'  {node_id}["{label}"];'

        lines: list[str] = ["flowchart TD;"]
        for node in self.nodes:
            lines.append(node_line(node))

        lines.append(f"  START([Start]) --> {id_map[self.entry_node]};")

        for edge in self.edges:
            source = id_map[edge.source]
            target = id_map[edge.target]
            if edge.label:
                label = edge.label.replace('"', '\\"')
                lines.append(f"  {source} -->|{label}| {target};")
            else:
                lines.append(f"  {source} --> {target};")

        for conditional in self.conditionals:
            source = id_map[conditional.source]
            for route in conditional.routes:
                target = id_map[route.target]
                label = (route.label or route.route_key).replace('"', '\\"')
                lines.append(f"  {source} -->|{label}| {target};")

        for group in self.parallel_groups:
            fan_out, fan_in = group[0], group[1]
            members = group[2:]
            fo = id_map[fan_out]
            fi = id_map[fan_in]
            for member in members:
                m = id_map[member]
                lines.append(f"  {fo} --> {m};")
                lines.append(f"  {m} --> {fi};")

        return "\n".join(lines) + "\n"


class GuardrailDefinition(FrozenModel):
    """
    One explicit rule your agent should keep following.

    Why this exists:
    - use a guardrail when you want one short rule to stay visible and explicit
      instead of hiding it inside a long system prompt
    - this is useful for rules such as grounding, uncertainty, or language

    How to use it:
    - write one guardrail per important rule
    - `guardrail_id` is a slug you invent — pick a short lowercase name that
      describes the rule, e.g. "grounding", "uncertainty", "scope". It does
      not need to match anything else.
    - keep `title` short (shown in inspection views)
    - write `description` as a direct instruction the model can follow
    - use guardrails for sharp, stable rules — not for tone or persona (those
      belong in the system prompt)

    Important:
    - a guardrail is prompt-level guidance, not a hard technical sandbox

    Example:
    ```python
    GuardrailDefinition(
        guardrail_id="grounding",
        title="Ground claims in corpus evidence",
        description="Do not present unsupported claims as if they came from corpus evidence.",
    )
    ```
    """

    guardrail_id: str = Field(
        ...,
        min_length=1,
        description=(
            "Stable identifier for this rule, for example `grounding` or `uncertainty`."
        ),
    )
    title: str = Field(
        ...,
        min_length=1,
        description="Short label for the rule, for example `Ground claims in corpus evidence`.",
    )
    description: str = Field(
        ...,
        min_length=1,
        description="The exact instruction the agent should follow.",
    )


class ToolSelectionPolicy(FrozenModel):
    """
    Declarative policy controlling how tool usage is explored in a ReAct turn.

    Practical presets:
    - default assistant: `allow_parallel_calls=False`, no explicit call limit
    - fast investigation: `allow_parallel_calls=True` for independent reads
    - strict mode: set `max_tool_calls_per_turn=1` to cap exploration
      (note: call limit is not enforced yet in the first v2 runtime)
    """

    allow_parallel_calls: bool = Field(
        default=False,
        description=(
            "Allow the runtime to execute independent tool calls in parallel."
        ),
    )
    max_tool_calls_per_turn: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Optional cap for tool calls in one assistant turn. Reserved for now: "
            "first v2 ReAct runtime does not enforce this limit yet."
        ),
    )


class ToolApprovalPolicy(FrozenModel):
    """
    Declarative human-approval policy for ReAct tool execution.

    Why this is separate from tool selection:
    - tool selection answers "may the agent call tools?"
    - tool approval answers "when must a human validate a tool call first?"

    How to read this policy:
    - `enabled=False`: no approval pauses
    - `enabled=True`: apply explicit tool list first, then runtime heuristics
      for read-only vs mutating tool names

    Example:
    - `enabled=True` and `always_require_tools=("delete_ticket",)` means
      `delete_ticket` always pauses for approval, and mutating tools like
      `update_*` also pause via heuristic.
    """

    enabled: bool = Field(
        default=False,
        description="Enable human approval checks before selected tool executions.",
    )
    always_require_tools: tuple[str, ...] = Field(
        default=(),
        description=(
            "Exact tool names that always require approval when enabled, "
            "for example ('delete_ticket', 'artifact.publish')."
        ),
    )


class ReActPolicy(FrozenModel):
    """
    Compact description of a broad tool-using assistant.

    This is the right abstraction when the developer wants to describe how the
    assistant should behave in general, not to script a workflow step by step.

    Prompt vs guardrails:
    - `system_prompt_template` is the broad strategy and tone
    - `guardrails` are explicit operating constraints attached as policy data

    Common policy shapes:
    - "Prompt only": no tools, no approval, no guardrails
    - "RAG helper": search tools + grounding/uncertainty guardrails
    - "Operations copilot": tools + explicit approval on risky actions
    """

    system_prompt_template: str | None = Field(
        ...,
        min_length=1,
        description=(
            "Primary assistant instructions rendered as the runtime system prompt."
        ),
    )
    tool_selection: ToolSelectionPolicy = Field(
        default_factory=ToolSelectionPolicy,
        description="How tool calls are selected and paced during a turn.",
    )
    tool_approval: ToolApprovalPolicy = Field(
        default_factory=ToolApprovalPolicy,
        description=(
            "When a tool call must pause for explicit human validation first."
        ),
    )
    guardrails: tuple[GuardrailDefinition, ...] = Field(
        default=(),
        description=(
            "Declarative behavioral constraints injected into runtime "
            "operating guidance."
        ),
    )


class ProxyTransportKind(str, Enum):
    """Transport mechanism used by proxy agents to reach external executors."""

    HTTP = "http"
    MCP = "mcp"
    QUEUE = "queue"


class ProxySpec(FrozenModel):
    """
    Typed transport target for a `ProxyAgentDefinition`.

    Exactly one target style is valid:
    - HTTP/MCP: `endpoint_url`
    - QUEUE: `queue_name`
    """

    transport: ProxyTransportKind
    endpoint_url: AnyUrl | None = None
    queue_name: str | None = None
    timeout_ms: int = Field(default=5000, ge=100)

    @model_validator(mode="after")
    def validate_target(self) -> "ProxySpec":
        if self.transport in {ProxyTransportKind.HTTP, ProxyTransportKind.MCP}:
            if self.endpoint_url is None:
                raise ValueError(
                    f"endpoint_url is required when transport={self.transport.value!r}."
                )
            if self.queue_name is not None:
                raise ValueError(
                    f"queue_name must be omitted when transport={self.transport.value!r}."
                )

        if self.transport == ProxyTransportKind.QUEUE:
            if self.queue_name is None:
                raise ValueError("queue_name is required when transport='queue'.")
            if self.endpoint_url is not None:
                raise ValueError("endpoint_url must be omitted when transport='queue'.")

        return self


class AgentDefinition(FrozenModel, ABC):
    """
    Pure declaration of a business-facing agent.

    Concrete subclasses describe the role, the editable business surface, and
    the execution style. Fred runtime turns that declaration into a live agent
    later.
    """

    agent_id: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    tags: tuple[str, ...] = ()
    fields: tuple[FieldSpec, ...] = ()
    tuning_values: dict[str, TuningValue] = Field(
        default_factory=dict,
        description=(
            "Runtime tuning values forwarded from control-plane enrollment. "
            "Keyed by FieldSpec.key. Read via context.tuning_values in graph steps "
            "or via definition.tuning_values in react prompting. "
            "Populated by _apply_runtime_tuning; do not set manually in agent definitions."
        ),
    )
    execution_category: ExecutionCategory
    public: bool = True
    """
    Whether this agent is a user-facing entry point.

    Public agents (the default) appear in /v1/models and /agents listings so
    that OpenAI-compatible frontends and developer tools can discover them.

    Set to False for sub-agents that are only invoked internally via
    context.invoke_agent() — e.g. the child agents of a TeamAgent in route
    mode.  They must still be registered so the runtime can find and execute
    them, but they should not be presented as top-level chat models.
    """

    def preview(self) -> AgentPreview:
        return AgentPreview.none(note="No preview provided by this agent definition.")

    def _build_inspection(
        self,
        *,
        declared_tool_refs: tuple[ToolRequirement, ...] = (),
        default_mcp_servers: tuple[MCPServerRef, ...] = (),
    ) -> AgentInspection:
        """
        Build the shared inspection payload for one agent definition.

        Why this exists:
        - all v2 agent families share the same safe inspection shape
        - only some families expose tool refs or MCP defaults, so the shared builder
          should accept those values explicitly instead of forcing them onto every base
          contract

        How to use:
        - call from `inspect()` in the concrete family with the tool/MCP surface
          that actually belongs to that family

        Example:
        - `return self._build_inspection(declared_tool_refs=self.declared_tool_refs, default_mcp_servers=self.default_mcp_servers)`
        """

        return AgentInspection(
            agent_id=self.agent_id,
            role=self.role,
            description=self.description,
            tags=self.tags,
            fields=self.fields,
            execution_category=self.execution_category,
            declared_tool_refs=declared_tool_refs,
            default_mcp_servers=default_mcp_servers,
            preview=self.preview(),
        )

    def inspect(self) -> AgentInspection:
        """
        Return the safe inspection payload for this agent definition.

        Why this exists:
        - callers need one non-activating introspection entrypoint on every v2 agent
        - the base contract should still work for agent families with no local tool
          declaration surface, such as proxy agents

        How to use:
        - call through `inspect_agent(...)` or directly on the definition

        Example:
        - `inspection = definition.inspect()`
        """

        return self._build_inspection()


class GraphAgentDefinition(AgentDefinition, ABC):
    """
    Authoring contract for workflow-shaped agents.

    Use this when the user experience depends on a clear business journey:
    qualify, identify, collect context, ask for approval, then act. The graph
    expresses that journey in a way that remains understandable to developers,
    product owners, and demo audiences.
    """

    execution_category: ExecutionCategory = ExecutionCategory.GRAPH
    declared_tool_refs: tuple[ToolRequirement, ...] = Field(
        default=(),
        description=(
            "Exact Fred tools declared by this workflow agent. "
            "Use this when graph nodes may invoke first-class Fred tools during "
            "execution."
        ),
    )
    default_mcp_servers: tuple[MCPServerRef, ...] = Field(
        default=(),
        description=(
            "Default MCP servers Fred should attach for this workflow agent. "
            "Use this when graph execution should see external MCP tools at runtime."
        ),
    )

    @abstractmethod
    def build_graph(self) -> GraphDefinition:
        """Return the pure structural graph definition."""

    @abstractmethod
    def input_model(self) -> type[BaseModel]:
        """Return the typed input model accepted by the graph runtime."""

    @abstractmethod
    def state_model(self) -> type[BaseModel]:
        """Return the typed mutable state model used during graph execution."""

    @abstractmethod
    def output_model(self) -> type[BaseModel]:
        """Return the typed final output model produced by the graph runtime."""

    conversation_history_max_turns: ClassVar[int] = 20
    """Maximum number of prior turns carried forward. Oldest-first truncation."""

    @abstractmethod
    def build_initial_state(
        self,
        input_model: BaseModel,
        binding: BoundRuntimeContext,
    ) -> BaseModel:
        """
        Build the initial graph state for one execution.

        This method MUST remain pure: it may derive values from the bound
        runtime context, but MUST NOT perform I/O.
        """

    def _turn_carry_fields(self) -> frozenset[str]:
        """
        Return the set of state field names that carry forward across turns.

        The default includes ``conversation_history`` when the state model
        declares it (i.e. inherits from ``ConversationalState``).  Override to
        add agent-specific continuity fields.
        """
        state_fields = self.state_model().model_fields
        if "conversation_history" in state_fields:
            return frozenset({"conversation_history"})
        return frozenset()

    def build_turn_state(
        self,
        input_model: BaseModel,
        binding: BoundRuntimeContext,
        previous_state: BaseModel | None = None,
        invocation_turns: tuple[ConversationTurn, ...] = (),
    ) -> BaseModel:
        """
        Build the initial state for a new turn, carrying forward continuity fields.

        Carry-forward policy (P1–P3 from the memory RFC):
        - Only fields declared by ``_turn_carry_fields()`` are carried from
          ``previous_state``; all other fields come from ``build_initial_state``.
        - When there is no ``previous_state`` but ``invocation_turns`` is
          non-empty, those turns seed ``conversation_history`` on the first
          callee turn so the sub-agent understands the caller's context.
        - Agents whose state does not include ``ConversationalState`` are
          completely unaffected by this default implementation.
        """
        base = self.build_initial_state(input_model, binding)
        carry_fields = self._turn_carry_fields()
        if not carry_fields:
            return base

        max_turns = self.__class__.conversation_history_max_turns

        if previous_state is not None:
            base_fields = set(type(base).model_fields)
            prev_fields = set(type(previous_state).model_fields)
            shared = carry_fields & base_fields & prev_fields
            updates: dict[str, object] = {}
            for field_name in shared:
                value = getattr(previous_state, field_name)
                if field_name == "conversation_history":
                    value = tuple(value[-max_turns:])
                updates[field_name] = value
            return base.model_copy(update=updates) if updates else base

        if invocation_turns and "conversation_history" in carry_fields:
            return base.model_copy(
                update={"conversation_history": tuple(invocation_turns[-max_turns:])}
            )

        return base

    def build_completed_state(self, state: BaseModel) -> BaseModel:
        """
        Normalize the terminal graph state before it is persisted.

        Called by the runtime after the last node completes and before
        checkpointing. The default implementation is the identity function.
        Override (or let ``TeamAgent`` auto-generate) to append a
        ``ConversationTurn`` so that turn N+1 sees the completed exchange.
        """
        return state

    @abstractmethod
    def node_handlers(self) -> Mapping[str, object]:
        """
        Return executable node handlers keyed by `GraphDefinition.node_id`.

        The runtime validates and binds these handlers; authors do not manage
        LangGraph directly.
        """

    @abstractmethod
    def build_output(self, state: BaseModel) -> BaseModel:
        """
        Build the final typed output from the terminal graph state.

        This method MUST remain pure.
        """

    def preview(self) -> AgentPreview:
        graph = self.build_graph()
        return AgentPreview(
            kind=PreviewKind.MERMAID,
            content=graph.to_mermaid(),
        )

    def inspect(self) -> AgentInspection:
        """
        Return the safe inspection payload for this workflow agent.

        Why this exists:
        - graph agents expose declared tool refs and optional MCP defaults as part of
          their executable contract
        - inspection should surface that without activating runtime dependencies

        How to use:
        - call when UI or backend needs the non-executable graph summary

        Example:
        - `inspection = graph_definition.inspect()`
        """

        return self._build_inspection(
            declared_tool_refs=self.declared_tool_refs,
            default_mcp_servers=self.default_mcp_servers,
        )


class ReActAgentDefinition(AgentDefinition, ABC):
    """
    Authoring contract for broad assistants and tool supervisors.

    Use this when the service is mainly conversational: understand the request,
    decide whether tools are useful, and answer naturally. The business value
    comes from flexibility, not from enforcing a fixed step-by-step process.
    """

    execution_category: ExecutionCategory = ExecutionCategory.REACT
    declared_tool_refs: tuple[ToolRequirement, ...] = Field(
        default=(),
        description=(
            "Exact Fred tools declared by this conversational agent. "
            "Use this for first-class Fred tool refs such as `knowledge.search`."
        ),
    )
    default_mcp_servers: tuple[MCPServerRef, ...] = Field(
        default=(),
        description=(
            "Default MCP servers Fred should attach for this conversational agent. "
            "Use this when external MCP tools should be available by default at runtime."
        ),
    )

    @abstractmethod
    def policy(self) -> ReActPolicy:
        """Return the pure ReAct policy used by the platform runtime."""

    def inspect(self) -> AgentInspection:
        """
        Return the safe inspection payload for this ReAct agent.

        Why this exists:
        - ReAct agents expose declared tool refs and optional MCP defaults as part of
          their authoring/runtime contract
        - inspection should show that surface without constructing LangChain tools

        How to use:
        - call when UI or backend needs the non-activating ReAct summary

        Example:
        - `inspection = react_definition.inspect()`
        """

        return self._build_inspection(
            declared_tool_refs=self.declared_tool_refs,
            default_mcp_servers=self.default_mcp_servers,
        )

    def preview(self) -> AgentPreview:
        policy = self.policy()
        tool_count = len(self.declared_tool_refs)
        guardrail_count = len(policy.guardrails)
        summary = (
            "ReAct runtime\n"
            f"- Declared tools: {tool_count}\n"
            f"- Guardrails: {guardrail_count}\n"
            f"- Parallel tool calls: {'yes' if policy.tool_selection.allow_parallel_calls else 'no'}\n"
            f"- Human approval: {'yes' if policy.tool_approval.enabled else 'no'}\n"
        )
        if policy.tool_selection.max_tool_calls_per_turn is not None:
            summary += f"- Max tool calls per turn: {policy.tool_selection.max_tool_calls_per_turn}\n"
        return AgentPreview(kind=PreviewKind.TEXT, content=summary)


class DeepAgentDefinition(ReActAgentDefinition, ABC):
    """
    Authoring contract for deep-agent style assistants.

    Runtime intent:
    - keep the same message/tool contract as ReAct
    - allow a dedicated deep runtime implementation
    """

    execution_category: ExecutionCategory = ExecutionCategory.DEEP


class ProxyAgentDefinition(AgentDefinition, ABC):
    """Authoring contract for agents delegated to an external runtime endpoint."""

    execution_category: ExecutionCategory = ExecutionCategory.PROXY

    @abstractmethod
    def proxy_spec(self) -> ProxySpec:
        """Return the pure proxy transport specification."""

    def preview(self) -> AgentPreview:
        spec = self.proxy_spec()
        target = (
            spec.queue_name
            if spec.transport == ProxyTransportKind.QUEUE
            else str(spec.endpoint_url)
        )
        summary = (
            "Proxy runtime\n"
            f"- Transport: {spec.transport.value}\n"
            f"- Target: {target}\n"
            f"- Timeout (ms): {spec.timeout_ms}\n"
        )
        return AgentPreview(kind=PreviewKind.TEXT, content=summary)
