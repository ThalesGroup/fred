"""
Core authoring contract for Fred v2 agents.

This module matters because it defines the language an agent author uses to
describe a business role in Fred. The important question is not "how do I wire
LangGraph?" but "what kind of service am I building for a user?"

The v2 contract therefore separates two families of agents:
- `ReActAgentDefinition` for assistants whose value comes from flexible
  conversation plus tools
- `GraphAgentDefinition` for services whose value comes from a clear business
  journey with explicit steps, decisions, and guarded actions

The models in this file are intentionally pure. They describe what the agent
is, what it needs, and what a developer or product owner should be able to
inspect safely before anything is executed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from enum import Enum
from typing import Annotated, Literal

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, model_validator

from agentic_backend.core.agents.agent_spec import FieldSpec, MCPServerRef

from .context import BoundRuntimeContext


class FrozenModel(BaseModel):
    """Shared strict model base for the v2 agent contract."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class ExecutionCategory(str, Enum):
    """Top-level execution family used by runtime dispatch and inspection."""

    GRAPH = "graph"
    REACT = "react"
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


class ToolRequirementBase(FrozenModel):
    """Common requirement fields shared by all tool requirement variants."""

    required: bool = True
    description: str | None = None


class ToolRefRequirement(ToolRequirementBase):
    """Requirement that names one concrete runtime tool (for example `knowledge.search`)."""

    kind: Literal["tool_ref"] = "tool_ref"
    tool_ref: str = Field(..., min_length=1)


class ToolCapabilityRequirement(ToolRequirementBase):
    """Requirement by abstract capability (reserved for future runtime resolution)."""

    kind: Literal["capability"] = "capability"
    capability: str = Field(..., min_length=1)


ToolRequirement = Annotated[
    ToolRefRequirement | ToolCapabilityRequirement,
    Field(discriminator="kind"),
]


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
    tool_requirements: tuple[ToolRequirement, ...] = ()
    default_mcp_servers: tuple[MCPServerRef, ...] = ()
    preview: AgentPreview = Field(default_factory=AgentPreview.none)


class GraphNodeDefinition(FrozenModel):
    """One named business step in a graph authoring definition."""

    node_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str | None = None
    shape: GraphNodeShape = GraphNodeShape.RECT


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
    """

    state_model_name: str = Field(..., min_length=1)
    entry_node: str = Field(..., min_length=1)
    nodes: tuple[GraphNodeDefinition, ...]
    edges: tuple[GraphEdgeDefinition, ...] = ()
    conditionals: tuple[GraphConditionalDefinition, ...] = ()

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

        return "\n".join(lines) + "\n"


class GuardrailDefinition(FrozenModel):
    """
    Declarative runtime guardrail for a ReAct assistant.

    Current v2 runtime behavior:
    - guardrails are visible in inspection and preview
    - guardrails are appended to the system prompt under
      "Operating guardrails"

    Why keep guardrails separate from `system_prompt_template`:
    - prompt text defines broad assistant behavior and persona
    - guardrails isolate non-negotiable operating constraints so they can be
      reviewed, counted, and tuned as explicit policy objects

    This remains instruction-level steering, not a hard sandbox.

    Typical examples:
    - grounding: "Only claim facts supported by retrieved evidence."
    - uncertainty: "If confidence is low, say what is missing."
    - language: "Answer in French unless the user asks another language."
    """

    guardrail_id: str = Field(
        ...,
        min_length=1,
        description=(
            "Stable technical identifier (for example: grounding, pii_redaction)."
        ),
    )
    title: str = Field(
        ...,
        min_length=1,
        description="Short human-readable label shown in inspection and debug views.",
    )
    description: str = Field(
        ...,
        min_length=1,
        description="Exact behavioral rule injected into ReAct operating guidance.",
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
    tool_requirements: tuple[ToolRequirement, ...] = ()
    default_mcp_servers: tuple[MCPServerRef, ...] = ()
    execution_category: ExecutionCategory

    def preview(self) -> AgentPreview:
        return AgentPreview.none(note="No preview provided by this agent definition.")

    def inspect(self) -> AgentInspection:
        return AgentInspection(
            agent_id=self.agent_id,
            role=self.role,
            description=self.description,
            tags=self.tags,
            fields=self.fields,
            execution_category=self.execution_category,
            tool_requirements=self.tool_requirements,
            default_mcp_servers=self.default_mcp_servers,
            preview=self.preview(),
        )


class GraphAgentDefinition(AgentDefinition, ABC):
    """
    Authoring contract for workflow-shaped agents.

    Use this when the user experience depends on a clear business journey:
    qualify, identify, collect context, ask for approval, then act. The graph
    expresses that journey in a way that remains understandable to developers,
    product owners, and demo audiences.
    """

    execution_category: Literal[ExecutionCategory.GRAPH] = ExecutionCategory.GRAPH

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

    def build_turn_state(
        self,
        input_model: BaseModel,
        binding: BoundRuntimeContext,
        previous_state: BaseModel | None = None,
    ) -> BaseModel:
        """
        Build the initial state for a new turn, optionally reusing prior session state.

        The default behavior is stateless. Override this when the business
        experience should feel continuous across turns, for example remembering
        which parcel, ticket, order, or case the user already selected.
        """
        return self.build_initial_state(input_model, binding)

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


class ReActAgentDefinition(AgentDefinition, ABC):
    """
    Authoring contract for broad assistants and tool supervisors.

    Use this when the service is mainly conversational: understand the request,
    decide whether tools are useful, and answer naturally. The business value
    comes from flexibility, not from enforcing a fixed step-by-step process.
    """

    execution_category: Literal[ExecutionCategory.REACT] = ExecutionCategory.REACT

    @abstractmethod
    def policy(self) -> ReActPolicy:
        """Return the pure ReAct policy used by the platform runtime."""

    def preview(self) -> AgentPreview:
        policy = self.policy()
        tool_count = len(self.tool_requirements)
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


class ProxyAgentDefinition(AgentDefinition, ABC):
    """Authoring contract for agents delegated to an external runtime endpoint."""

    execution_category: Literal[ExecutionCategory.PROXY] = ExecutionCategory.PROXY

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
