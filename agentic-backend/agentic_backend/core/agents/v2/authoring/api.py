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
Agent-author-facing helpers to write ReAct v2 agents with small Python tools.

Use this module when you want a simple pattern:
- declare one `ReActAgent` definition
- write plain `@tool` functions
- keep prompts in markdown resources

This layer hides runtime plumbing so agent code stays close to business intent.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, TypeVar, overload

from fred_core.store import VectorSearchHit
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from pydantic_core import PydanticUndefined

from agentic_backend.core.agents.agent_spec import FieldSpec, FieldType, UIHints

from ..contracts.context import (
    ArtifactPublishRequest,
    ArtifactScope,
    BoundRuntimeContext,
    FetchedResource,
    PublishedArtifact,
    ResourceFetchRequest,
    ResourceScope,
    ToolInvocationRequest,
    ToolInvocationResult,
    UiPart,
)
from ..contracts.models import ReActAgentDefinition, ReActPolicy, ToolRefRequirement
from ..resources import load_agent_prompt_markdown
from .authored_tool_runtime import (
    _AUTHOR_TOOL_ATTR,
    _AuthorTool,
    ensure_toolset_registered,
    normalize_tool,
)
from .legacy_runtime_bridge import _AuthorRuntime
from .tool_args_schema import build_args_schema
from .tool_context_helpers import ToolContextHelpers

_M = TypeVar("_M", bound=BaseModel)
_T = TypeVar("_T")


@dataclass(frozen=True)
class ToolOutput:
    """
    Simple return object for a Python-authored tool.

    Why this exists:
    - use this when your tool needs to return more than plain text
    - it lets you return a short message, optional JSON data, optional UI
      links, and optional sources in one object

    How to use it:
    - in most tools, return `context.text(...)`, `context.json(...)`, or
      `context.error(...)`
    - instantiate `ToolOutput` yourself only when you want a custom
      combination of text, data, UI parts, or sources

    Example::

        ```python
        return ToolOutput(text="Processed 3 records", data={"count": 3})
        ```
    """

    text: str | None = None
    data: dict[str, object] | None = None
    ui_parts: tuple[UiPart, ...] = ()
    sources: tuple[VectorSearchHit, ...] = ()
    is_error: bool = False


_MISSING: Any = object()


class ResourceNotFoundError(KeyError):
    """
    Raised by ``ctx.read_resource()`` when the requested key does not exist
    in the agent config workspace.

    Why this exists:
    - gives authored tools a concrete exception to catch instead of a bare
      ``KeyError`` or an opaque runtime error
    - makes the error contract visible at import time, next to the SDK API

    How to use it:
    - catch it in your tool when a missing resource is a recoverable condition

    Example::

        ```python
        except ResourceNotFoundError:
            return ctx.error("Template not uploaded yet.")
        ```
    """


class ResourceFetchError(RuntimeError):
    """
    Raised by ``ctx.read_resource()`` when a non-404 storage error occurs
    (network failure, permission denied, corrupted object, etc.).

    Why this exists:
    - distinguishes transient / infrastructure errors from a plain missing key
    - lets authored tools decide whether to retry, fall back, or propagate

    How to use it:
    - catch it alongside ``ResourceNotFoundError`` when you want to handle
      infrastructure failures separately from missing resources

    Example::

        ```python
        except ResourceFetchError as exc:
            return ctx.error(f"Storage error while reading template: {exc}")
        ```
    """


class ArtifactPublicationError(RuntimeError):
    """
    Raised by ``ctx.publish_bytes()`` when the storage backend rejects the
    upload (network failure, quota exceeded, permission denied, etc.).

    Why this exists:
    - gives authored tools a typed exception instead of a raw infrastructure
      error leaking through the SDK boundary

    How to use it:
    - catch it when you want to surface a clear error message rather than an
      opaque traceback

    Example::

        ```python
        except ArtifactPublicationError as exc:
            return ctx.error(f"Could not save the generated file: {exc}")
        ```
    """


class ModelInvocationError(RuntimeError):
    """
    Raised by ``ctx.extract_structured()`` when the LLM call fails (network
    error, model timeout, schema validation failure, etc.).

    Why this exists:
    - gives authored tools a typed exception instead of a raw LangChain or
      Pydantic error leaking through the SDK boundary

    How to use it:
    - catch it when you want to surface a clear error message rather than an
      opaque traceback

    Example::

        ```python
        except ModelInvocationError as exc:
            return ctx.error(f"Could not extract slide content: {exc}")
        ```
    """


class ToolInvocationError(RuntimeError):
    """
    Raised by ``ctx.invoke_tool()`` when the target tool is unknown or when
    the tool call itself raises an unhandled exception.

    Why this exists:
    - gives authored tools a typed exception instead of a raw RuntimeError or
      infrastructure error leaking through the SDK boundary

    How to use it:
    - catch it when your tool delegates to another Fred tool and you want to
      handle failures gracefully

    Example::

        ```python
        except ToolInvocationError as exc:
            return ctx.error(f"Search failed: {exc}")
        ```
    """


class ToolContext:
    """
    Small runtime helper injected as the first argument of every authored tool.

    Why this exists:
    - every `@tool(...)` function needs one object that lets it use Fred
      runtime features without learning runtime internals

    How to use it:
    - accept `context: ToolContext` as the first parameter of a `@tool(...)`
      function
    - then call only the helpers you need:
      `config(...)`, `invoke_tool(...)`, `extract_structured(...)`,
      `read_resource(...)`, `publish_*`, `text(...)`, `json(...)`, `error(...)`
    - ignore advanced details such as `binding`
    - use `context.helpers` only when you intentionally want optional Fred
      shortcuts

    Example::

        ```python
        template_key = ctx.config("ppt_template_key")
        result = await ctx.invoke_tool("knowledge.search", query="policy", top_k=5)
        artifact = await ctx.publish_text(file_name="report.md", content="# Report")
        return ctx.text("Done")
        ```
    """

    def __init__(self, runtime: _AuthorRuntime) -> None:
        self._runtime = runtime
        self._sources: list[VectorSearchHit] = []
        self._helpers = ToolContextHelpers(self)

    @property
    def binding(self) -> BoundRuntimeContext:
        """
        Advanced escape hatch to the bound runtime context.

        Why this exists:
        - keep this only for rare cases where no dedicated `ToolContext`
          helper exists

        How to use it:
        - most authors should ignore it
        - prefer the higher-level helpers on `ToolContext` first

        Example::

            ```python
            session_id = ctx.binding.portable_context.session_id
            ```
        """
        return self._runtime.binding

    @property
    def helpers(self) -> ToolContextHelpers:
        """
        Optional Fred-specific shortcuts.

        Why this exists:
        - the main `ToolContext` stays generic
        - this groups the few shortcuts that are specific to Fred usage

        How to use it:
        - ignore this in normal generic tools
        - use it only when your tool really needs one of those shortcuts

        Example::

            ```python
            bundle = await ctx.helpers.search_corpus_many((("retention policy", 5),))
            ```
        """
        return self._helpers

    async def invoke_tool(
        self,
        tool_ref: str,
        /,
        **payload: object,
    ) -> ToolInvocationResult:
        """
        Call another Fred tool from inside your Python-authored tool.

        Why this exists:
        - lets your tool reuse existing built-in, authored, or provider-backed
          tools instead of reimplementing the same logic

        How to use it:
        - pass the target `tool_ref`
        - pass that tool's inputs as keyword arguments
        - use the returned result when you need sources, UI parts, or raw data

        Example::

            ```python
            result = await ctx.invoke_tool("knowledge.search", query="policy", top_k=5)
            ```
        """
        try:
            result = await self._runtime.tool_invoker.invoke(
                ToolInvocationRequest(
                    tool_ref=tool_ref,
                    payload=dict(payload),
                    context=self.binding.portable_context,
                )
            )
        except ToolInvocationError:
            raise
        except Exception as exc:
            raise ToolInvocationError(
                f"Tool '{tool_ref}' invocation failed: {exc}"
            ) from exc
        self._record_sources(result.sources)
        return result

    async def extract_structured(
        self,
        output_model: type[_M],
        *,
        prompt: str,
        text: str,
    ) -> _M:
        """
        Turn free text into a Pydantic model with the current agent model.

        Why this exists:
        - use this when your tool has raw text and you want a validated
          structured result without touching model SDK APIs

        How to use it:
        - pass the output model you want
        - pass a short extraction prompt
        - pass the text to parse

        Example::

            ```python
            parsed = await ctx.extract_structured(
                MySchema, prompt="Extract fields", text=raw_text
            )
            ```
        """
        try:
            model = self._runtime.model.with_structured_output(
                output_model,
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
        except ModelInvocationError:
            raise
        except Exception as exc:
            raise ModelInvocationError(
                f"Structured extraction failed ({output_model.__name__}): {exc}"
            ) from exc

    async def read_resource(
        self,
        key: str,
        *,
        scope: ResourceScope = ResourceScope.AGENT_CONFIG,
        target_user_id: str | None = None,
    ) -> FetchedResource:
        """
        Read one Fred-managed resource by key.

        Why this exists:
        - use this when your tool needs a packaged prompt fragment, config
          file, or other stored resource

        How to use it:
        - pass the resource key
        - optionally override the scope

        Example::

            ```python
            resource = await ctx.read_resource("instructions.md")
            ```
        """
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

    @overload
    def config(self, key: str) -> Any: ...
    @overload
    def config(self, key: str, *, default: _T) -> _T: ...

    def config(self, key: str, *, default: Any = _MISSING) -> Any:
        """
        Read one field value from the agent's current configuration.

        Why this exists:
        - use this when your tool needs a value the admin or author configured,
          such as a template key, output format, or threshold

        How to use it:
        - pass the field name exactly as declared on the agent definition class
        - use dotted paths to reach nested fields
        - pass `default=` to avoid a `KeyError` when the field may be absent;
          the return type matches the type of the default value

        Example::

            ```python
            template_key = ctx.config("ppt_template_key")                    # -> Any
            size         = ctx.config("font_size_pt", default=14)             # -> int
            attach       = ctx.config("chat_options.attach_files", default=False)  # -> bool
            ```
        """
        obj: Any = self._runtime.definition
        for part in key.split("."):
            try:
                obj = getattr(obj, part)
            except AttributeError:
                if default is not _MISSING:
                    return default
                raise KeyError(
                    f"Agent configuration has no field '{key}'. "
                    f"Declare it on the agent definition class."
                ) from None
        return obj

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
        """
        Publish bytes as a downloadable file for the user.

        Why this exists:
        - use this when your tool generates a file such as a spreadsheet,
          image, or presentation

        How to use it:
        - pass the output file name
        - pass the bytes to publish

        Example::

            ```python
            artifact = await ctx.publish_bytes(file_name="report.xlsx", content=xlsx_bytes)
            ```
        """
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
        """
        Publish text as a downloadable file for the user.

        Why this exists:
        - this is the easiest way to return a generated `.txt`, `.md`, or
          similar text file

        How to use it:
        - pass the file name
        - pass the text content

        Example::

            ```python
            artifact = await ctx.publish_text(file_name="summary.md", content="# Summary")
            ```
        """
        return await self.publish_bytes(
            file_name=file_name,
            content=content.encode("utf-8"),
            content_type=content_type,
            title=title,
            key=key,
            scope=scope,
        )

    async def fetch_media(self, document_uid: str, file_name: str) -> bytes:
        """
        Load media bytes linked from a packaged markdown document.

        Why this exists:
        - use this when your tool needs the raw bytes of an image or attached
          media file referenced from a document

        How to use it:
        - pass the document uid and media file name

        Example::

            ```python
            content = await ctx.fetch_media(document_uid="doc-1", file_name="figure.png")
            ```
        """
        return await self._runtime.fetch_media(document_uid, file_name)

    def text(self, text: str) -> ToolOutput:
        """
        Return a simple successful text result.

        Why this exists:
        - this is the normal way to return a short human-readable result

        How to use it:
        - pass the text you want the assistant to see

        Example::

            ```python
            return ctx.text("Completed")
            ```
        """
        return ToolOutput(text=text, sources=self._collected_sources())

    def json(
        self,
        data: BaseModel | Mapping[str, object],
        *,
        text: str | None = None,
    ) -> ToolOutput:
        """
        Return JSON-style data, with optional text.

        Why this exists:
        - use this when your tool should return structured data that another
          tool or later step may reuse

        How to use it:
        - pass a Pydantic model or a dict
        - optionally add a short text message

        Example::

            ```python
            return ctx.json({"total": 3}, text="Computed total")
            ```
        """
        payload = data.model_dump() if isinstance(data, BaseModel) else dict(data)
        return ToolOutput(
            text=text,
            data=payload,
            sources=self._collected_sources(),
        )

    def error(self, message: str) -> ToolOutput:
        """
        Return a handled error message.

        Why this exists:
        - use this when the tool cannot continue and you want to return a clear
          message without raising an unexpected exception

        How to use it:
        - pass the message you want the assistant to receive

        Example::

            ```python
            return ctx.error("Missing account id.")
            ```
        """
        return ToolOutput(
            text=message,
            sources=self._collected_sources(),
            is_error=True,
        )

    def link(self, artifact: PublishedArtifact, *, text: str = "") -> ToolOutput:
        """
        Return a published artifact as a clickable download link.

        Why this exists:
        - every tool that publishes a file follows the same pattern:
          ``ToolOutput(text=..., ui_parts=(artifact.to_link_part(),))``
        - this collapses that into one readable line

        How to use it:
        - call ``ctx.publish_bytes()`` or ``ctx.publish_text()`` first
        - pass the returned artifact and an optional summary text

        Example::

            ```python
            artifact = await ctx.publish_bytes(file_name="report.pdf", content=pdf_bytes)
            return ctx.link(artifact, text="Report ready.")
            ```
        """
        return ToolOutput(
            text=text or None,
            ui_parts=(artifact.to_link_part(),),
            sources=self._collected_sources(),
        )

    def _record_sources(self, sources: Sequence[VectorSearchHit]) -> None:
        """
        Collect search sources observed while this tool executes.

        Why this exists:
        - authored tools may call other Fred tools that return sources, and the
          convenience output builders should keep those sources attached

        How to use it:
        - internal runtime helper only; authored tools should not call this
          directly

        """
        existing = {(source.uid, source.content[:100]) for source in self._sources}
        for source in sources:
            key = (source.uid, source.content[:100])
            if key in existing:
                continue
            existing.add(key)
            self._sources.append(source)

    def _collected_sources(self) -> tuple[VectorSearchHit, ...]:
        """
        Return the collected sources seen during this tool call.

        Why this exists:
        - output helpers need one place to read the sources accumulated through
          previous nested tool invocations

        How to use it:
        - internal runtime helper only; authored tools should not call this
          directly

        """
        return tuple(self._sources)


def prompt_md(*, package: str, file_name: str) -> str:
    """
    Load a Markdown prompt file from your agent package.

    Why this exists:
    - lets you keep long prompts in `.md` files instead of inline Python
      strings

    How to use it:
    - pass your package path
    - pass the markdown file name inside that package

    Example::

        ```python
        system_prompt_template = prompt_md(
            package="my_pkg.agents.search", file_name="system_prompt.md"
        )
        ```
    """
    return load_agent_prompt_markdown(package=package, file_name=file_name)


def tool(
    tool_ref: str,
    *,
    description: str | None = None,
    runtime_name: str | None = None,
    args_schema: type[BaseModel] | None = None,
    success_message: str | None = None,
) -> Callable[[Callable[..., object]], Callable[..., object]]:
    """
    Mark a Python function as a tool for a `ReActAgent`.

    Why this exists:
    - use this decorator when you want the agent to be able to call your Python
      function as a tool
    - most small tools should not need a separate Pydantic args model: Fred
      builds that input schema from your function signature automatically

    How to use it:
    - decorate the function
    - make the first parameter `context: ToolContext`
    - define the remaining parameters as the tool inputs
    - add normal Python type annotations such as `str`, `int`, `bool`, or a
      Pydantic model field type so Fred can validate inputs
    - give the tool a clear `tool_ref` and description
    - only pass `args_schema=...` if you explicitly want to override the schema
      inferred from the function signature

    Example::

        ```python
        @tool("acme.math.add", description="Add two numbers.")
        async def add(ctx: ToolContext, a: int, b: int) -> ToolOutput:
            return ctx.text(f"{a} + {b} = {a + b}")
        ```
    """

    def decorator(fn: Callable[..., object]) -> Callable[..., object]:
        authored_tool = _AuthorTool(
            tool_ref=tool_ref,
            runtime_name=(runtime_name or fn.__name__).strip(),
            description=description,
            args_schema=args_schema or build_args_schema(fn),
            handler=fn,
            success_message=success_message,
        )
        setattr(fn, _AUTHOR_TOOL_ATTR, authored_tool)
        return fn

    return decorator


def ui_field(
    default: Any = ...,
    *,
    title: str,
    description: str,
    ui_type: FieldType,
    required: bool = False,
    ui: UIHints | None = None,
    **kwargs: Any,
) -> Any:
    """
    Declare an agent configuration field with UI metadata — once.

    Why this exists:
    - the old pattern required declaring the field twice: as a Pydantic ``Field``
      and again as a ``FieldSpec`` inside the ``fields`` tuple
    - ``ui_field()`` replaces both: the ``FieldSpec`` is derived automatically
      from the metadata stored here, so the ``fields`` tuple can be omitted

    How to use it:
    - use it exactly like ``pydantic.Field()``, but add ``title``, ``ui_type``,
      and optionally ``ui`` (``UIHints``)
    - declare the field on the agent class — no separate ``fields`` tuple needed
    - omit ``default`` (or pass ``...``) to make the field required

    Example::

        ```python
        ppt_template_key: str = ui_field(
            "simple_template.pptx",
            title="Template key",
            description="Filename of the .pptx template.",
            ui_type="text",
            ui=UIHints(group="PowerPoint"),
        )
        ```
    """
    extra: dict[str, Any] = {
        "_ui_type": ui_type,
        "_ui_required": required,
    }
    if ui is not None:
        extra["_ui_hints"] = ui.model_dump()
    if default is ...:
        return Field(
            title=title, description=description, json_schema_extra=extra, **kwargs
        )
    return Field(
        default=default,
        title=title,
        description=description,
        json_schema_extra=extra,
        **kwargs,
    )


def _derive_fields(cls: type) -> tuple[FieldSpec, ...]:
    """
    Build ``FieldSpec`` tuples from any field declared with ``ui_field()``.

    Why this exists:
    - ``ReActAgent.__pydantic_init_subclass__`` calls this to auto-populate
      the ``fields`` tuple so authors don't have to maintain it manually

    How to use it:
    - internal hook; authored agents should use ``ui_field()`` and rely on
      automatic derivation rather than calling this directly
    """
    specs: list[FieldSpec] = []
    for field_name, field_info in cls.model_fields.items():
        extra = field_info.json_schema_extra
        if not isinstance(extra, dict):
            continue
        ui_type = extra.get("_ui_type")
        if not ui_type:
            continue
        raw_default = field_info.default
        default = None if raw_default is PydanticUndefined else raw_default
        ui_hints_data = extra.get("_ui_hints", {})
        specs.append(
            FieldSpec(
                key=field_name,
                type=ui_type,
                title=field_info.title or field_name.replace("_", " ").title(),
                description=field_info.description,
                default=default,
                required=extra.get("_ui_required", False),
                ui=UIHints(**ui_hints_data) if ui_hints_data else UIHints(),
            )
        )
    return tuple(specs)


class ReActAgent(ReActAgentDefinition):
    """
    Base class for a Python-authored ReAct agent.

    Why this exists:
    - use this when you want to define an agent in Python with a prompt and a
      small set of local tools

    How to use it:
    - subclass `ReActAgent`
    - set `agent_id`, `role`, `description`, and `system_prompt_template`
    - list your `@tool(...)` functions in `tools = (...)`

    Example:
    - `class TutorialAgent(ReActAgent): tools = (add_numbers,)`
    """

    tools: ClassVar[tuple[Callable[..., object], ...]] = ()
    system_prompt_template: str
    toolset_key: str = ""
    declared_tool_refs: tuple[ToolRefRequirement, ...] = ()

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: object) -> None:
        """
        Turn locally authored `@tool(...)` functions into Fred declared tool refs.

        Why this exists:
        - local Python tools are authoring sugar, not a separate runtime tool model
        - ReAct authoring should still expose explicit declared tool refs for
          inspection, validation, and runtime binding

        How to use:
        - define local tools in `tools = (...)`
        - let this hook register the toolset and populate `declared_tool_refs`

        Example:
        - `class MyAgent(ReActAgent): tools = (latest_policy_summary,)`
        """

        super().__pydantic_init_subclass__(**kwargs)

        needs_rebuild = False

        # Register authored tools declared in `tools = (...)`
        authored_tools = tuple(normalize_tool(tool_obj) for tool_obj in cls.tools)
        cls.__authored_tools__ = authored_tools
        if authored_tools:
            toolset_key = cls._authored_toolset_key()
            ensure_toolset_registered(cls, toolset_key, authored_tools)
            cls.model_fields["toolset_key"].default = toolset_key
            cls.model_fields["declared_tool_refs"].default = tuple(
                ToolRefRequirement(
                    tool_ref=authored_tool.tool_ref,
                    description=authored_tool.description,
                )
                for authored_tool in authored_tools
            )
            needs_rebuild = True

        # Auto-derive `fields` from ui_field() annotations when the subclass
        # has not explicitly declared a `fields` tuple of its own.
        if "fields" not in cls.__annotations__:
            derived = _derive_fields(cls)
            if derived:
                cls.model_fields["fields"].default = derived
                needs_rebuild = True

        if needs_rebuild:
            cls.model_rebuild(force=True)

    @classmethod
    def _authored_toolset_key(cls) -> str:
        """
        Resolve the stable toolset key for one authored ReAct agent class.

        Why this exists:
        - locally authored tools need one stable registry key before runtime binding
        - authors should not have to hand-write that key in the common case

        How to use:
        - call while registering authored tools for the class

        Example:
        - `toolset_key = cls._authored_toolset_key()`
        """

        current = cls.model_fields["toolset_key"].default
        if isinstance(current, str) and current.strip():
            return current.strip()
        return f"authored.{cls.__module__}.{cls.__name__}"

    def policy(self) -> ReActPolicy:
        """
        Return the minimal ReAct policy for a locally authored ReAct agent.

        Why this exists:
        - `ReActAgent` is authoring sugar over `ReActAgentDefinition`
        - the common case only needs the authored system prompt here because
          `declared_tool_refs` already carries the tool contract separately

        How to use:
        - set `system_prompt_template` on the class and inherit this default method

        Example:
        - `class SearchAgent(ReActAgent): system_prompt_template = "..."`
        """

        return ReActPolicy(system_prompt_template=self.system_prompt_template)


__all__ = [
    "ArtifactPublicationError",
    "ModelInvocationError",
    "ReActAgent",
    "ResourceFetchError",
    "ResourceNotFoundError",
    "ToolContext",
    "ToolInvocationError",
    "ToolOutput",
    "UIHints",
    "prompt_md",
    "tool",
    "ui_field",
]
