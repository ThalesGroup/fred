"""
Platform runtime contract for Fred v2 agents.

This file is where Fred stops being "a set of agent classes" and becomes a
runtime platform. The author defines the role and the behavior shape elsewhere;
the runtime defined here is responsible for turning that declaration into a
reliable user experience.

From a business point of view, this layer matters because it owns the things
users notice when they stop being toy demos:
- continuity across turns
- safe human approval
- visible tool activity
- portable pause/resume semantics
- stable final outputs such as maps, links, and citations
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Generic, Literal, TypeAlias, TypeVar

from fred_core import VectorSearchHit
from fred_core.kpi import BaseKPIWriter
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.types import Checkpointer
from pydantic import BaseModel, ConfigDict, Field

from .context import (
    ArtifactPublishRequest,
    BoundRuntimeContext,
    FetchedResource,
    JsonScalar,
    PortableContext,
    ResourceFetchRequest,
    PublishedArtifact,
    ToolInvocationRequest,
    ToolInvocationResult,
    UiPart,
)
from .models import AgentDefinition


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class CheckpointStrategy(str, Enum):
    SESSION = "session"
    EXCHANGE = "exchange"
    DISABLED = "disabled"


class RuntimeEventKind(str, Enum):
    STATUS = "status"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    AWAITING_HUMAN = "awaiting_human"
    ASSISTANT_DELTA = "assistant_delta"
    FINAL = "final"


class ExecutionConfig(FrozenModel):
    """
    Per-run execution instructions supplied by the platform.

    This is not authoring data. It describes how one concrete run should be
    executed: which conversation thread it belongs to, whether it is a resume,
    and how much intermediate activity should be surfaced.
    """

    checkpoint_strategy: CheckpointStrategy = CheckpointStrategy.SESSION
    thread_id: str | None = None
    checkpoint_id: str | None = None
    max_steps: int = Field(default=100, ge=1)
    stream_intermediate_events: bool = True
    resume_payload: object | None = None


class RuntimeEventBase(FrozenModel):
    sequence: int = Field(default=0, ge=0)


class StatusRuntimeEvent(RuntimeEventBase):
    kind: Literal[RuntimeEventKind.STATUS] = RuntimeEventKind.STATUS
    status: str = Field(..., min_length=1)
    detail: str | None = None


class ToolCallRuntimeEvent(RuntimeEventBase):
    kind: Literal[RuntimeEventKind.TOOL_CALL] = RuntimeEventKind.TOOL_CALL
    tool_name: str = Field(..., min_length=1)
    call_id: str = Field(..., min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)


class ToolResultRuntimeEvent(RuntimeEventBase):
    kind: Literal[RuntimeEventKind.TOOL_RESULT] = RuntimeEventKind.TOOL_RESULT
    call_id: str = Field(..., min_length=1)
    content: str = Field(default="")
    tool_name: str | None = None
    is_error: bool = False
    sources: tuple[VectorSearchHit, ...] = ()
    ui_parts: tuple[UiPart, ...] = ()


class HumanChoiceOption(FrozenModel):
    id: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    description: str | None = None
    default: bool = False


class HumanInputRequest(FrozenModel):
    """
    Structured pause presented to a user.

    The goal is to expose a real business decision, not a raw runtime mechanic.
    A user should see "choose the parcel" or "approve the reroute", not an
    implementation detail of the graph engine.
    """

    stage: str | None = None
    title: str | None = None
    question: str | None = None
    choices: tuple[HumanChoiceOption, ...] = ()
    free_text: bool = False
    metadata: dict[str, JsonScalar] = Field(default_factory=dict)
    checkpoint_id: str | None = None


class AwaitingHumanRuntimeEvent(RuntimeEventBase):
    kind: Literal[RuntimeEventKind.AWAITING_HUMAN] = RuntimeEventKind.AWAITING_HUMAN
    request: HumanInputRequest


class AssistantDeltaRuntimeEvent(RuntimeEventBase):
    kind: Literal[RuntimeEventKind.ASSISTANT_DELTA] = RuntimeEventKind.ASSISTANT_DELTA
    delta: str = Field(..., min_length=1)


class FinalRuntimeEvent(RuntimeEventBase):
    kind: Literal[RuntimeEventKind.FINAL] = RuntimeEventKind.FINAL
    content: str = Field(default="")
    sources: tuple[VectorSearchHit, ...] = ()
    ui_parts: tuple[UiPart, ...] = ()
    model_name: str | None = None
    token_usage: dict[str, int] | None = None
    finish_reason: str | None = None


RuntimeEvent: TypeAlias = Annotated[
    StatusRuntimeEvent
    | ToolCallRuntimeEvent
    | ToolResultRuntimeEvent
    | AwaitingHumanRuntimeEvent
    | AssistantDeltaRuntimeEvent
    | FinalRuntimeEvent,
    Field(discriminator="kind"),
]


class SpanPort(ABC):
    @abstractmethod
    def set_attribute(self, key: str, value: JsonScalar) -> None:
        """Attach a scalar attribute to the current span."""

    @abstractmethod
    def end(self) -> None:
        """Finish the span."""


class TracerPort(ABC):
    @abstractmethod
    def start_span(
        self,
        *,
        name: str,
        context: PortableContext,
        attributes: Mapping[str, JsonScalar] | None = None,
    ) -> SpanPort:
        """Start a span bound to the portable execution context."""


class TokenProviderPort(ABC):
    @abstractmethod
    def get_bearer_token(self, binding: BoundRuntimeContext) -> str:
        """Return a bearer token appropriate for the currently bound runtime."""


class ChatModelFactoryPort(ABC):
    @abstractmethod
    def build(
        self, definition: AgentDefinition, binding: BoundRuntimeContext
    ) -> BaseChatModel:
        """
        Resolve the canonical chat model for the currently bound agent runtime.

        This port exists so v2 runtimes stay platform-owned and testable:
        agent definitions remain pure declarations, while model selection stays
        an injected capability that Fred can later align with a broader SDK.
        """


class ToolInvokerPort(ABC):
    @abstractmethod
    async def invoke(self, request: ToolInvocationRequest) -> ToolInvocationResult:
        """Invoke a tool through the platform's transport layer."""


class ToolProviderPort(ABC):
    @abstractmethod
    def bind(self, binding: BoundRuntimeContext) -> None:
        """Refresh context-scoped tool-provider state for the current runtime."""

    @abstractmethod
    async def activate(self) -> None:
        """Initialize any heavy provider resources before tool execution."""

    @abstractmethod
    def get_tools(self) -> tuple[BaseTool, ...]:
        """Return the current runtime-provided tool set."""

    @abstractmethod
    async def aclose(self) -> None:
        """Release provider resources."""


class ArtifactPublisherPort(ABC):
    @abstractmethod
    def bind(self, binding: BoundRuntimeContext) -> None:
        """Refresh context-scoped publishing state for the current runtime."""

    @abstractmethod
    async def publish(self, request: ArtifactPublishRequest) -> PublishedArtifact:
        """Store a generated artifact and return its downloadable description."""


class ResourceReaderPort(ABC):
    @abstractmethod
    def bind(self, binding: BoundRuntimeContext) -> None:
        """Refresh context-scoped resource access state for the current runtime."""

    @abstractmethod
    async def fetch(self, request: ResourceFetchRequest) -> FetchedResource:
        """Read an existing Fred-managed resource such as a template or note."""


class WorkspaceClientPort(ABC):
    """
    Low-level escape hatch for context-scoped workspace clients.

    Preferred v2 path:
    - use `ArtifactPublisherPort` to publish generated files
    - use `ResourceReaderPort` to fetch existing templates/resources

    This marker remains available for edge cases, but serious business agents
    should not need to learn raw workspace client methods.
    """


class WorkspaceClientFactoryPort(ABC):
    @abstractmethod
    def build(self, binding: BoundRuntimeContext) -> WorkspaceClientPort:
        """Build a context-scoped workspace client during bind()."""


@dataclass(frozen=True, slots=True)
class RuntimeServices:
    """
    Platform-owned business capabilities injected into a runtime.

    These services answer practical questions for the runtime:
    - how do I talk to the chosen model?
    - how do I reach platform tools and MCP servers?
    - how do I persist and resume a paused conversation?
    - how do I attach the right user-scoped workspace or token?

    Keeping them explicit is what lets a graph or ReAct definition stay focused
    on the business role instead of hiding infrastructure decisions in agent
    code.
    """

    tracer: TracerPort | None = None
    chat_model_factory: ChatModelFactoryPort | None = None
    token_provider: TokenProviderPort | None = None
    tool_invoker: ToolInvokerPort | None = None
    tool_provider: ToolProviderPort | None = None
    artifact_publisher: ArtifactPublisherPort | None = None
    resource_reader: ResourceReaderPort | None = None
    workspace_client_factory: WorkspaceClientFactoryPort | None = None
    kpi: BaseKPIWriter | None = None
    checkpointer: Checkpointer = None


InputModelT = TypeVar("InputModelT", bound=BaseModel)
OutputModelT = TypeVar("OutputModelT", bound=BaseModel)
DefinitionT = TypeVar("DefinitionT", bound=AgentDefinition)


class Executor(ABC, Generic[InputModelT, OutputModelT]):
    @abstractmethod
    async def invoke(
        self, input_model: InputModelT, config: ExecutionConfig
    ) -> OutputModelT:
        """Execute the agent once and return the final output."""

    @abstractmethod
    def stream(
        self, input_model: InputModelT, config: ExecutionConfig
    ) -> AsyncIterator[RuntimeEvent]:
        """Execute the agent and yield runtime events."""


class AgentRuntime(ABC, Generic[DefinitionT, InputModelT, OutputModelT]):
    """
    Platform-owned shell that turns a pure definition into a live agent.

    The lifecycle is intentionally narrow:
    - bind() is cheap and re-runnable
    - activate() is heavy and runs at most once per runtime instance
    - get_executor() is the only official executable entrypoint

    This matters because a real business agent must survive changing user
    context, refreshed tokens, transport changes, and eventually multiple
    adapters such as WebSocket and Temporal without redefining its behavior.
    """

    def __init__(self, *, definition: DefinitionT, services: RuntimeServices):
        self._definition = definition
        self._services = services
        self._binding: BoundRuntimeContext | None = None
        self._activated = False
        self._disposed = False
        self._workspace_client: WorkspaceClientPort | None = None
        self._executor: Executor[InputModelT, OutputModelT] | None = None

    @property
    def definition(self) -> DefinitionT:
        return self._definition

    @property
    def services(self) -> RuntimeServices:
        return self._services

    @property
    def binding(self) -> BoundRuntimeContext:
        if self._binding is None:
            raise RuntimeError("AgentRuntime is not bound. Call bind() first.")
        return self._binding

    @property
    def workspace_client(self) -> WorkspaceClientPort | None:
        return self._workspace_client

    @property
    def is_activated(self) -> bool:
        return self._activated

    @property
    def is_disposed(self) -> bool:
        return self._disposed

    def bind(self, binding: BoundRuntimeContext) -> None:
        if self._disposed:
            raise RuntimeError("Cannot bind a disposed AgentRuntime.")

        self._binding = binding
        self._workspace_client = (
            self._services.workspace_client_factory.build(binding)
            if self._services.workspace_client_factory is not None
            else None
        )
        self._executor = None
        self.on_bind(binding)

    def on_bind(self, binding: BoundRuntimeContext) -> None:
        """Optional hook for subclasses to rebuild context-scoped helper state."""

    async def activate(self) -> None:
        if self._disposed:
            raise RuntimeError("Cannot activate a disposed AgentRuntime.")
        if self._activated:
            return
        binding = self.binding
        await self.on_activate(binding)
        self._activated = True

    async def on_activate(self, binding: BoundRuntimeContext) -> None:
        """Optional hook for one-time heavy activation logic."""

    async def get_executor(self) -> Executor[InputModelT, OutputModelT]:
        if self._disposed:
            raise RuntimeError("Cannot build an executor from a disposed AgentRuntime.")

        await self.activate()
        binding = self.binding
        if self._executor is None:
            self._executor = await self.build_executor(binding)
        return self._executor

    @abstractmethod
    async def build_executor(
        self, binding: BoundRuntimeContext
    ) -> Executor[InputModelT, OutputModelT]:
        """Return the canonical executor for the currently bound runtime."""

    async def dispose(self) -> None:
        if self._disposed:
            return
        try:
            await self.on_dispose()
        finally:
            self._disposed = True
            self._executor = None
            self._workspace_client = None
            self._binding = None

    async def on_dispose(self) -> None:
        """Optional hook for resource cleanup."""
