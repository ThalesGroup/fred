"""
Developer-facing helpers to write ReAct v2 agents with small Python tools.

Use this module when you want a simple pattern:
- declare one `ReActAgent` definition
- write plain `@tool` functions
- keep prompts in markdown resources

This layer hides runtime plumbing so agent code stays close to business intent.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, cast, get_type_hints

from fred_core import VectorSearchHit, get_keycloak_client_id, get_keycloak_url
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, create_model

from agentic_backend.common.kf_markdown_media_client import KfMarkdownMediaClient
from agentic_backend.common.structures import AgentSettings
from agentic_backend.common.user_token_refresher import (
    refresh_user_access_token_from_keycloak,
)

from .context import (
    ArtifactPublishRequest,
    ArtifactScope,
    BoundRuntimeContext,
    FetchedResource,
    PublishedArtifact,
    ResourceFetchRequest,
    ResourceScope,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationRequest,
    ToolInvocationResult,
    UiPart,
)
from .models import ReActAgentDefinition, ReActPolicy, ToolRefRequirement
from .prompt_resources import load_agent_prompt_markdown
from .runtime import ToolInvokerPort
from .toolset_registry import (
    ToolHandler,
    ToolRefSpec,
    ToolsetRegistration,
    ToolsetRuntimePorts,
    get_toolset_registration,
    register_toolset,
)

_AUTHOR_TOOL_ATTR = "__fred_v2_author_tool__"
_MAX_UNIQUE_CHUNKS = 40


@dataclass(frozen=True)
class SearchBundle:
    text: str
    ranked_filenames: tuple[str, ...]
    hits: tuple[VectorSearchHit, ...]


@dataclass(frozen=True)
class ToolOutput:
    text: str | None = None
    data: dict[str, object] | None = None
    ui_parts: tuple[UiPart, ...] = ()
    sources: tuple[VectorSearchHit, ...] = ()
    is_error: bool = False


@dataclass(frozen=True)
class _AuthorTool:
    tool_ref: str
    runtime_name: str
    description: str | None
    args_schema: type[BaseModel]
    handler: Callable[..., object]
    success_message: str | None = None


class _MarkdownMediaAgentShim:
    def __init__(
        self, *, binding: BoundRuntimeContext, settings: AgentSettings
    ) -> None:
        self.runtime_context = binding.runtime_context
        self.agent_settings = settings

    def refresh_user_access_token(self) -> str:
        refresh_token = self.runtime_context.refresh_token
        if not refresh_token:
            raise RuntimeError(
                "Cannot refresh user access token: refresh_token missing from runtime context."
            )

        keycloak_url = get_keycloak_url()
        client_id = get_keycloak_client_id()
        if not keycloak_url:
            raise RuntimeError(
                "User security realm_url is not configured for Keycloak."
            )
        if not client_id:
            raise RuntimeError(
                "User security client_id is not configured for Keycloak."
            )

        payload = refresh_user_access_token_from_keycloak(
            keycloak_url=keycloak_url,
            client_id=client_id,
            refresh_token=refresh_token,
        )
        new_access_token = payload.get("access_token")
        new_refresh_token = payload.get("refresh_token") or refresh_token
        if not isinstance(new_access_token, str) or not new_access_token:
            raise RuntimeError(
                "Keycloak refresh response did not include a valid access_token."
            )
        self.runtime_context.access_token = new_access_token
        self.runtime_context.refresh_token = new_refresh_token
        return new_access_token


class _AuthorRuntime:
    def __init__(
        self,
        *,
        definition: ReActAgentDefinition,
        binding: BoundRuntimeContext,
        settings: AgentSettings,
        ports: ToolsetRuntimePorts,
    ) -> None:
        self.definition = definition
        self.binding = binding
        self.settings = settings
        self.ports = ports
        self._model = None
        self._media_client: KfMarkdownMediaClient | None = None

    @property
    def model(self):
        if self._model is None:
            if self.ports.chat_model_factory is None:
                raise RuntimeError(
                    "Authored local tools require RuntimeServices.chat_model_factory."
                )
            self._model = self.ports.chat_model_factory.build(
                self.definition, self.binding
            )
        return self._model

    @property
    def tool_invoker(self) -> ToolInvokerPort:
        invoker = self.ports.fallback_tool_invoker
        if invoker is None:
            raise RuntimeError(
                "Authored local tools require a fallback tool invoker for Fred capabilities."
            )
        return invoker

    async def fetch_media(self, document_uid: str, file_name: str) -> bytes:
        if self._media_client is None:
            from agentic_backend.core.agents.agent_flow import AgentFlow

            self._media_client = KfMarkdownMediaClient(
                agent=cast(
                    AgentFlow,
                    _MarkdownMediaAgentShim(
                        binding=self.binding,
                        settings=self.settings,
                    ),
                )
            )
        return await self._media_client.fetch_media(document_uid, file_name)


class ToolContext:
    """
    Runtime helper object injected as first argument of every authored tool.

    What you typically use:
    - `search(...)` / `search_many(...)` to query corpus
    - `extract_structured(...)` to parse model output into pydantic
    - `publish_text(...)` to return downloadable artifacts
    - `text(...)`, `json(...)`, `error(...)` to format tool output

    You never instantiate `ToolContext` manually.
    """

    def __init__(self, runtime: _AuthorRuntime) -> None:
        self._runtime = runtime
        self._sources: list[VectorSearchHit] = []

    @property
    def binding(self) -> BoundRuntimeContext:
        return self._runtime.binding

    def setting_text(self, key: str, *, default: str = "") -> str:
        tuning = self._runtime.settings.tuning
        if tuning is None:
            return default
        for field in tuning.fields:
            if field.key != key:
                continue
            if isinstance(field.default, str) and field.default.strip():
                return field.default.strip()
        return default

    async def search(
        self,
        query: str,
        *,
        top_k: int = 8,
    ) -> tuple[VectorSearchHit, ...]:
        result = await self._runtime.tool_invoker.invoke(
            ToolInvocationRequest(
                tool_ref="knowledge.search",
                payload={"query": query, "top_k": top_k},
                context=self.binding.portable_context,
            )
        )
        self._record_sources(result.sources)
        return result.sources

    async def search_many(
        self,
        queries: Sequence[tuple[str, int]],
        *,
        context_hint: str = "",
    ) -> SearchBundle:
        all_hits: list[VectorSearchHit] = []
        seen: set[tuple[str, str]] = set()

        for query, top_k in queries:
            rendered_query = (
                f"{query}\nContexte: {context_hint}" if context_hint else query
            )
            hits = await self.search(rendered_query, top_k=top_k)
            for hit in hits:
                dedupe_key = (hit.uid, hit.content[:100])
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                all_hits.append(hit)

        if not all_hits:
            return SearchBundle(text="", ranked_filenames=(), hits=())

        all_hits.sort(key=lambda hit: hit.score or 0.0, reverse=True)
        top_hits = tuple(all_hits[:_MAX_UNIQUE_CHUNKS])

        filename_scores: dict[str, float] = {}
        for hit in top_hits:
            file_name = hit.file_name or hit.title or hit.uid
            filename_scores[file_name] = filename_scores.get(file_name, 0.0) + float(
                hit.score or 0.0
            )
        ranked_filenames = tuple(
            sorted(
                filename_scores,
                key=lambda name: filename_scores[name],
                reverse=True,
            )
        )

        formatted_chunks = []
        for index, hit in enumerate(top_hits, start=1):
            title = hit.title or hit.file_name or hit.uid
            formatted_chunks.append(
                f"### Extrait {index} (source: {title})\n{hit.content}"
            )
        return SearchBundle(
            text="\n\n".join(formatted_chunks),
            ranked_filenames=ranked_filenames,
            hits=top_hits,
        )

    async def extract_structured(
        self,
        output_model: type[BaseModel],
        *,
        prompt: str,
        text: str,
    ) -> BaseModel:
        model = self._runtime.model.with_structured_output(
            _schema_without_max_length(output_model),
            method="json_schema",
        )
        result = await model.ainvoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content=text),
            ]
        )
        if isinstance(result, output_model):
            return result
        if isinstance(result, dict):
            return output_model.model_validate(result)
        return output_model.model_validate(dict(result))

    async def read_resource(
        self,
        key: str,
        *,
        scope: ResourceScope = ResourceScope.AGENT_CONFIG,
        target_user_id: str | None = None,
    ) -> FetchedResource:
        reader = self._runtime.ports.resource_reader
        if reader is None:
            raise RuntimeError(
                "Authored local tools require RuntimeServices.resource_reader."
            )
        return await reader.fetch(
            ResourceFetchRequest(
                key=key,
                scope=scope,
                target_user_id=target_user_id,
            )
        )

    async def publish_bytes(
        self,
        *,
        file_name: str,
        content: bytes,
        content_type: str | None = None,
        title: str | None = None,
        key: str | None = None,
        scope: ArtifactScope = ArtifactScope.USER,
    ) -> PublishedArtifact:
        publisher = self._runtime.ports.artifact_publisher
        if publisher is None:
            raise RuntimeError(
                "Authored local tools require RuntimeServices.artifact_publisher."
            )
        return await publisher.publish(
            ArtifactPublishRequest(
                file_name=file_name,
                content_bytes=content,
                content_type=content_type,
                title=title,
                key=key,
                scope=scope,
            )
        )

    async def publish_text(
        self,
        *,
        file_name: str,
        content: str,
        content_type: str = "text/plain; charset=utf-8",
        title: str | None = None,
        key: str | None = None,
        scope: ArtifactScope = ArtifactScope.USER,
    ) -> PublishedArtifact:
        return await self.publish_bytes(
            file_name=file_name,
            content=content.encode("utf-8"),
            content_type=content_type,
            title=title,
            key=key,
            scope=scope,
        )

    async def fetch_media(self, document_uid: str, file_name: str) -> bytes:
        return await self._runtime.fetch_media(document_uid, file_name)

    def text(self, text: str) -> ToolOutput:
        return ToolOutput(text=text, sources=self._collected_sources())

    def json(
        self,
        data: BaseModel | Mapping[str, object],
        *,
        text: str | None = None,
    ) -> ToolOutput:
        payload = data.model_dump() if isinstance(data, BaseModel) else dict(data)
        return ToolOutput(
            text=text,
            data=payload,
            sources=self._collected_sources(),
        )

    def error(self, message: str) -> ToolOutput:
        return ToolOutput(
            text=message,
            sources=self._collected_sources(),
            is_error=True,
        )

    def _record_sources(self, sources: Sequence[VectorSearchHit]) -> None:
        existing = {(source.uid, source.content[:100]) for source in self._sources}
        for source in sources:
            key = (source.uid, source.content[:100])
            if key in existing:
                continue
            existing.add(key)
            self._sources.append(source)

    def _collected_sources(self) -> tuple[VectorSearchHit, ...]:
        return tuple(self._sources)


def prompt_md(*, package: str, file_name: str) -> str:
    return load_agent_prompt_markdown(package=package, file_name=file_name)


def tool(
    tool_ref: str,
    *,
    description: str | None = None,
    runtime_name: str | None = None,
    args_schema: type[BaseModel] | None = None,
    success_message: str | None = None,
) -> Callable[[Callable[..., object]], Callable[..., object]]:
    """Decorator to register a Python function as an executable tool for a ReActAgent.

    This decorator attaches metadata to a function, allowing the v2 authoring
    framework to understand its schema, description, and how to invoke it.
    The decorated function becomes a building block for a `ReActAgent`.

    The first argument of any decorated function MUST be `context: ToolContext`.
    The framework uses this to provide runtime capabilities like search.
    Function arguments can have type hints and default values, which are used to
    automatically generate the tool's argument schema for the agent.

    Args:
        tool_ref: The unique, namespaced identifier for this tool (e.g., "my_company.my_tool.v1").
            This is how the tool is identified in backend systems.
        description: A detailed, natural-language description of what the tool does,
            what its inputs are, and what it returns. This is critical for helping
            the agent decide when to use the tool.
        runtime_name: Optional. A short, snake_case name for the tool that the agent will
            use in its thought process (e.g., "knowledge_search"). If omitted, it
            defaults to the function name.
        args_schema: Optional. A Pydantic model to use for the arguments. If omitted,
            one is automatically generated from the function's type hints.
        success_message: Optional. A static message to return to the agent on
            successful execution if the tool function returns `None`.

    Example:
        ```python
        from agentic_backend.core.agents.v2.authoring import tool, ToolContext, ToolOutput
        from pydantic import BaseModel, Field

        @tool(
            "acme.document.search.v1",
            description="Searches for documents matching a natural-language query."
        )
        def search_documents(
            context: ToolContext,
            query: str = Field(..., description="The user's search query."),
            top_k: int = Field(5, description="The maximum number of documents to return.")
        ) -> ToolOutput:
            '''Searches for documents and returns the top results.'''
            hits = await context.search(query, top_k=top_k)
            if not hits:
                return context.text(f"No documents found for query: '{query}'.")
            return context.text(
                f"Found {len(hits)} documents matching the query: '{query}'."
            )
        ```
    """

    def decorator(fn: Callable[..., object]) -> Callable[..., object]:
        authored_tool = _AuthorTool(
            tool_ref=tool_ref,
            runtime_name=(runtime_name or fn.__name__).strip(),
            description=description,
            args_schema=args_schema or _build_args_schema(fn),
            handler=fn,
            success_message=success_message,
        )
        setattr(fn, _AUTHOR_TOOL_ATTR, authored_tool)
        return fn

    return decorator


class ReActAgent(ReActAgentDefinition):
    """Declarative base class for a ReAct-style assistant.

    Use this class to define a new agent whose behavior is primarily driven
    by a system prompt and a set of available tools. The v2 runtime handles
    the low-level ReAct loop (Think, Act, Observe).

    The author's responsibility is to declare the agent's properties, its
    tools, and its prompt. The platform handles the rest.

    Attributes:
        agent_id: A unique identifier for the agent (e.g., "my.company.my_agent.v1").
        role: A short, human-readable name for the agent (e.g., "Customer Support Assistant").
        description: A one-sentence summary of what the agent does.
        tools: A tuple of functions decorated with `@tool(...)`. These are the
            capabilities the agent can execute.
        system_prompt_template: The core system prompt that guides the agent.
            It's recommended to load this from a separate .md file using `prompt_md`.

    Example:
        A simple agent that can search for documents.

        First, define the tool in `tools.py`:
        ```python
        # src/my_package/agents/search_agent/tools.py

        from agentic_backend.core.agents.v2.authoring import tool, ToolContext, ToolOutput

        @tool("knowledge.search", description="Searches for relevant documents.")
        def search(
            context: ToolContext,
            query: str,
        ) -> ToolOutput:
            '''Searches for documents and returns the top results.'''
            hits = await context.search(query, top_k=5)
            # The text in the ToolOutput is what the agent sees as the tool's result.
            return context.text(
                f"Found {len(hits)} documents matching the query: '{query}'."
            )
        ```

        Then, define the agent in `agent.py`:
        ```python
        # src/my_package/agents/search_agent/agent.py

        from agentic_backend.core.agents.v2.authoring import ReActAgent, prompt_md
        from .tools import search

        class SearchAgent(ReActAgent):
            agent_id: str = "internal.acme.search_agent.v1"
            role: str = "Search Assistant"
            description: str = "Answers questions by searching the knowledge base."

            tools = (search,)
            system_prompt_template: str = prompt_md(
                package="my_package.agents.search_agent",
                file_name="system_prompt.md",
            )
    """

    tools: ClassVar[tuple[Callable[..., object], ...]] = ()
    system_prompt_template: str
    toolset_key: str = ""
    tool_requirements: tuple[ToolRefRequirement, ...] = ()

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: object) -> None:
        super().__pydantic_init_subclass__(**kwargs)

        authored_tools = tuple(_normalize_tool(tool_obj) for tool_obj in cls.tools)
        cls.__authored_tools__ = authored_tools

        if authored_tools:
            toolset_key = cls._authored_toolset_key()
            _ensure_toolset_registered(cls, toolset_key, authored_tools)
            cls.model_fields["toolset_key"].default = toolset_key
            cls.model_fields["tool_requirements"].default = tuple(
                ToolRefRequirement(
                    tool_ref=authored_tool.tool_ref,
                    description=authored_tool.description,
                )
                for authored_tool in authored_tools
            )
            cls.model_rebuild(force=True)

    @classmethod
    def _authored_toolset_key(cls) -> str:
        current = cls.model_fields["toolset_key"].default
        if isinstance(current, str) and current.strip():
            return current.strip()
        return f"authored.{cls.__module__}.{cls.__name__}"

    def policy(self) -> ReActPolicy:
        return ReActPolicy(system_prompt_template=self.system_prompt_template)


def _build_args_schema(fn: Callable[..., object]) -> type[BaseModel]:
    signature = inspect.signature(fn)
    parameters = list(signature.parameters.values())
    if not parameters:
        raise TypeError(
            f"Authored tool {fn.__name__} must accept a first ToolContext parameter."
        )

    fields: dict[str, tuple[object, object]] = {}
    type_hints = get_type_hints(fn, include_extras=True)
    for parameter in parameters[1:]:
        if parameter.kind not in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            raise TypeError(
                f"Authored tool {fn.__name__} uses unsupported parameter kind for {parameter.name!r}."
            )
        annotation = type_hints.get(parameter.name, Any)
        default = (
            ... if parameter.default is inspect.Parameter.empty else parameter.default
        )
        fields[parameter.name] = (annotation, default)

    model_name = "".join(part.capitalize() for part in fn.__name__.split("_")) + "Args"
    return create_model(model_name, **cast(dict[str, Any], fields))


def _schema_without_max_length(model_class: type[BaseModel]) -> type[BaseModel]:
    fields: dict[str, tuple[object, object]] = {}
    for name, field_info in model_class.model_fields.items():
        fields[name] = (
            field_info.annotation,
            Field(
                default=field_info.default,
                description=field_info.description,
            ),
        )
    return create_model(model_class.__name__, **cast(dict[str, Any], fields))


def _normalize_tool(tool_obj: object) -> _AuthorTool:
    authored_tool = getattr(tool_obj, _AUTHOR_TOOL_ATTR, None)
    if not isinstance(authored_tool, _AuthorTool):
        raise TypeError(
            "ReActAgent.tools must contain functions decorated with @tool(...)."
        )
    return authored_tool


def _ensure_toolset_registered(
    cls: type[ReActAgent],
    toolset_key: str,
    authored_tools: tuple[_AuthorTool, ...],
) -> None:
    if get_toolset_registration(toolset_key) is not None:
        return

    def _bind_handlers(
        definition: object,
        binding: BoundRuntimeContext,
        settings: AgentSettings,
        ports: ToolsetRuntimePorts,
    ) -> Mapping[str, ToolHandler]:
        runtime = _AuthorRuntime(
            definition=cast(ReActAgentDefinition, definition),
            binding=binding,
            settings=settings,
            ports=ports,
        )
        return {
            authored_tool.tool_ref: _bind_tool_handler(authored_tool, runtime)
            for authored_tool in authored_tools
        }

    register_toolset(
        ToolsetRegistration(
            toolset_key=toolset_key,
            tool_specs={
                authored_tool.tool_ref: ToolRefSpec(
                    tool_ref=authored_tool.tool_ref,
                    runtime_name=authored_tool.runtime_name,
                    args_schema=authored_tool.args_schema,
                    description=authored_tool.description,
                )
                for authored_tool in authored_tools
            },
            bind_handlers=_bind_handlers,
        )
    )


def _bind_tool_handler(
    authored_tool: _AuthorTool,
    runtime: _AuthorRuntime,
) -> ToolHandler:
    async def handle(request: ToolInvocationRequest) -> ToolInvocationResult:
        payload_model = authored_tool.args_schema.model_validate(request.payload)
        payload = payload_model.model_dump()
        context = ToolContext(runtime)
        value = authored_tool.handler(context, **payload)
        if inspect.isawaitable(value):
            value = await cast(Awaitable[object], value)
        return _coerce_tool_return(
            tool_ref=request.tool_ref,
            value=value,
            context=context,
            success_message=authored_tool.success_message,
        )

    return handle


def _coerce_tool_return(
    *,
    tool_ref: str,
    value: object,
    context: ToolContext,
    success_message: str | None,
) -> ToolInvocationResult:
    collected_sources = context._collected_sources()

    if isinstance(value, ToolInvocationResult):
        return value

    if isinstance(value, ToolOutput):
        return ToolInvocationResult(
            tool_ref=tool_ref,
            blocks=_build_blocks(text=value.text, data=value.data),
            ui_parts=value.ui_parts,
            sources=value.sources or collected_sources,
            is_error=value.is_error,
        )

    if isinstance(value, PublishedArtifact):
        text = success_message or f"Generated {value.file_name}."
        return ToolInvocationResult(
            tool_ref=tool_ref,
            blocks=_build_blocks(text=text, data=None),
            ui_parts=(value.to_link_part(),),
            sources=collected_sources,
        )

    if isinstance(value, BaseModel):
        return ToolInvocationResult(
            tool_ref=tool_ref,
            blocks=_build_blocks(
                text=success_message,
                data=value.model_dump(),
            ),
            sources=collected_sources,
        )

    if isinstance(value, Mapping):
        return ToolInvocationResult(
            tool_ref=tool_ref,
            blocks=_build_blocks(
                text=success_message,
                data=dict(value),
            ),
            sources=collected_sources,
        )

    if isinstance(value, str):
        return ToolInvocationResult(
            tool_ref=tool_ref,
            blocks=_build_blocks(text=value, data=None),
            sources=collected_sources,
        )

    if value is None:
        return ToolInvocationResult(
            tool_ref=tool_ref,
            blocks=_build_blocks(text=success_message, data=None),
            sources=collected_sources,
        )

    return ToolInvocationResult(
        tool_ref=tool_ref,
        blocks=_build_blocks(text=str(value), data=None),
        sources=collected_sources,
    )


def _build_blocks(
    *, text: str | None, data: dict[str, object] | None
) -> tuple[ToolContentBlock, ...]:
    blocks: list[ToolContentBlock] = []
    if text:
        blocks.append(ToolContentBlock(kind=ToolContentKind.TEXT, text=text))
    if data is not None:
        blocks.append(ToolContentBlock(kind=ToolContentKind.JSON, data=data))
    return tuple(blocks)


__all__ = [
    "ReActAgent",
    "SearchBundle",
    "ToolContext",
    "ToolOutput",
    "prompt_md",
    "tool",
]
