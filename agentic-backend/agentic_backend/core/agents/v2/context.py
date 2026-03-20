from __future__ import annotations

from enum import Enum
from typing import Annotated

from fred_core.store import VectorSearchHit
from pydantic import BaseModel, ConfigDict, Field

from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.chatbot.chat_schema import GeoPart, LinkKind, LinkPart


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class PortableEnvironment(str, Enum):
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


JsonScalar = str | int | float | bool | None


class PortableContext(FrozenModel):
    """
    Portable cross-platform execution context.

    This is intentionally narrower than Fred RuntimeContext and aligns with the
    capability-oriented SDK shape: correlation, identity, environment, and small
    non-sensitive baggage.
    """

    request_id: str = Field(..., min_length=1)
    correlation_id: str = Field(..., min_length=1)
    actor: str = Field(..., min_length=1)
    tenant: str = Field(..., min_length=1)
    environment: PortableEnvironment
    trace_id: str | None = None
    client_app: str | None = None
    agent_id: str | None = None
    agent_name: str | None = None
    agent_version: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    user_name: str | None = None
    team_id: str | None = None
    baggage: dict[str, str] = Field(default_factory=dict)


class ToolInvocationRequest(FrozenModel):
    tool_ref: str = Field(..., min_length=1)
    payload: dict[str, object] = Field(default_factory=dict)
    context: PortableContext
    timeout_ms: int = Field(default=5000, ge=100)
    idempotency_key: str | None = None


class ToolContentKind(str, Enum):
    TEXT = "text"
    JSON = "json"


class ToolContentBlock(FrozenModel):
    kind: ToolContentKind
    text: str | None = None
    data: dict[str, object] | None = None


UiPart = Annotated[LinkPart | GeoPart, Field(discriminator="type")]


class ToolInvocationResult(FrozenModel):
    tool_ref: str = Field(..., min_length=1)
    blocks: tuple[ToolContentBlock, ...] = ()
    sources: tuple[VectorSearchHit, ...] = ()
    ui_parts: tuple[UiPart, ...] = ()
    is_error: bool = False


class ArtifactScope(str, Enum):
    """
    Where a generated file should live in Fred.

    This is a business choice, not an implementation detail:
    - `USER` for files handed back to the end user
    - `AGENT_CONFIG` for agent-managed shared assets
    - `AGENT_USER` for agent-private notes scoped to one user
    """

    USER = "user"
    AGENT_CONFIG = "agent_config"
    AGENT_USER = "agent_user"


class ResourceScope(str, Enum):
    """
    Where an already-existing Fred resource should be read from.

    This is the other half of artifact publication:
    - admins upload shared templates and configuration under `AGENT_CONFIG`
    - users and agents exchange generated files under `USER`
    - agents can keep per-user notes or resources under `AGENT_USER`
    """

    USER = "user"
    AGENT_CONFIG = "agent_config"
    AGENT_USER = "agent_user"


class ArtifactPublishRequest(FrozenModel):
    """
    Typed request to publish a generated artifact through Fred storage.

    The goal is to let agents express "publish this report for the user" without
    hard-coding URLs, storage paths, or transport details.
    """

    file_name: str = Field(..., min_length=1)
    content_bytes: bytes = Field(..., min_length=1)
    scope: ArtifactScope = ArtifactScope.USER
    key: str | None = None
    content_type: str | None = None
    title: str | None = None
    link_kind: LinkKind = LinkKind.download
    target_user_id: str | None = None


class PublishedArtifact(FrozenModel):
    """
    Stable description of a file that Fred stored for an agent run.

    Returning this object instead of a raw URL keeps the capability explicit and
    makes it easy to convert the result into the UI-facing `LinkPart`.
    """

    scope: ArtifactScope
    key: str = Field(..., min_length=1)
    file_name: str = Field(..., min_length=1)
    size: int = Field(..., ge=0)
    href: str | None = None
    document_uid: str | None = None
    mime: str | None = None
    title: str | None = None
    link_kind: LinkKind = LinkKind.download

    def to_link_part(self) -> LinkPart:
        return LinkPart(
            href=self.href,
            title=self.title or self.file_name,
            kind=self.link_kind,
            mime=self.mime,
            document_uid=self.document_uid,
            file_name=self.file_name,
        )


class ResourceFetchRequest(FrozenModel):
    """
    Typed request to read a resource that already exists in Fred storage.

    This gives v2 agents a clear business story for templates and supporting
    assets: ask Fred for "the configured template" or "the per-user note",
    rather than constructing storage URLs or workspace paths by hand.
    """

    key: str = Field(..., min_length=1)
    scope: ResourceScope = ResourceScope.AGENT_CONFIG
    target_user_id: str | None = None


class FetchedResource(FrozenModel):
    """
    Stable description of a resource fetched from Fred storage.

    A business node can inspect metadata, decode text when appropriate, or pass
    the bytes to a downstream renderer without knowing anything about the
    underlying workspace transport.
    """

    scope: ResourceScope
    key: str = Field(..., min_length=1)
    file_name: str = Field(..., min_length=1)
    size: int = Field(..., ge=0)
    content_bytes: bytes = Field(default=b"")
    content_type: str | None = None

    def as_text(self, *, encoding: str = "utf-8") -> str:
        return self.content_bytes.decode(encoding)


class BoundRuntimeContext(FrozenModel):
    """
    Platform bind result combining the Fred RuntimeContext with a portable
    context that can be propagated through tracing, tool invocation, and
    future registry integrations.
    """

    runtime_context: RuntimeContext
    portable_context: PortableContext
