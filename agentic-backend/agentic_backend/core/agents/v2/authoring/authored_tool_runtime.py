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
Private authored-tool registration and coercion helpers.

Audience:
- `Fred developer` only
- this file is internal v2 SDK/runtime glue
- agent authors should not read or import anything from here

Why this module exists:
- `authoring/api.py` should stay focused on the small public SDK surface an
  agent author reads
- authored Python tools still need private machinery to register toolsets,
  build runtime handlers, and normalize Python return values into Fred tool
  results

How to use it:
- import these helpers only from `authoring/api.py`
- agent authors should never import this module directly

Example:
- `_ensure_toolset_registered(MyAgent, toolset_key, authored_tools)`
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel

from agentic_backend.common.structures import AgentSettings

from ..contracts.context import (
    BoundRuntimeContext,
    PublishedArtifact,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationRequest,
    ToolInvocationResult,
)
from ..contracts.models import ReActAgentDefinition
from ..support.authored_toolsets import (
    AuthoredToolHandler,
    AuthoredToolRuntimePorts,
    AuthoredToolsetRegistration,
    AuthoredToolSpec,
    get_authored_toolset_registration,
    register_authored_toolset,
)
from .legacy_runtime_bridge import _AuthorRuntime

if TYPE_CHECKING:
    from .api import ReActAgent, ToolContext

logger = logging.getLogger(__name__)

_AUTHOR_TOOL_ATTR = "__fred_v2_author_tool__"


@dataclass(frozen=True)
class _AuthorTool:
    """
    Private normalized authored-tool declaration.

    Why this exists:
    - the public `@tool(...)` decorator stores metadata on plain Python
      functions, but the runtime glue needs one explicit typed record while
      registering toolsets and binding handlers

    How to use it:
    - create from the `tool(...)` decorator
    - consume from the registration helpers in this module

    Example:
    - `authored_tool = _AuthorTool(tool_ref="knowledge.search", runtime_name="search", description=None, args_schema=ArgsModel, handler=fn)`
    """

    tool_ref: str
    runtime_name: str
    description: str | None
    args_schema: type[BaseModel]
    handler: Callable[..., object]
    success_message: str | None = None


def normalize_tool(tool_obj: object) -> _AuthorTool:
    """
    Validate and extract one authored tool declaration from a Python object.

    Why this exists:
    - `ReActAgent.tools` should fail fast if an author forgot the `@tool(...)`
      decorator

    How to use it:
    - call while normalizing one item from `ReActAgent.tools`

    Example:
    - `authored_tool = normalize_tool(search_documents)`
    """
    authored_tool = getattr(tool_obj, _AUTHOR_TOOL_ATTR, None)
    if not isinstance(authored_tool, _AuthorTool):
        raise TypeError(
            "ReActAgent.tools must contain functions decorated with @tool(...)."
        )
    return authored_tool


def ensure_toolset_registered(
    cls: type["ReActAgent"],
    toolset_key: str,
    authored_tools: tuple[_AuthorTool, ...],
) -> None:
    """
    Register one authored toolset in the process-local authored-tool registry.

    Why this exists:
    - authored Python functions are available at import time, but the runtime
      later rebuilds an agent from a definition and needs a stable lookup key

    How to use it:
    - call once during `ReActAgent` subclass initialization

    Example:
    - `ensure_toolset_registered(MyAgent, "authored.my_pkg.MyAgent", authored_tools)`
    """
    if get_authored_toolset_registration(toolset_key) is not None:
        return

    def _bind_handlers(
        definition: ReActAgentDefinition,
        binding: BoundRuntimeContext,
        settings: AgentSettings,
        ports: AuthoredToolRuntimePorts,
    ) -> Mapping[str, AuthoredToolHandler]:
        # This callback is intentionally deferred.
        #
        # At class-definition time we only know:
        # - the authored Python functions
        # - their tool metadata
        #
        # We do NOT yet have the runtime binding, settings, or runtime ports
        # needed to execute those tools. So we register this callback now and
        # the runtime bootstrap calls it later when the concrete runtime exists.
        runtime = _AuthorRuntime(
            definition=definition,
            binding=binding,
            settings=settings,
            ports=ports,
        )
        return {
            authored_tool.tool_ref: _bind_tool_handler(authored_tool, runtime)
            for authored_tool in authored_tools
        }

    register_authored_toolset(
        AuthoredToolsetRegistration(
            toolset_key=toolset_key,
            tool_specs={
                authored_tool.tool_ref: AuthoredToolSpec(
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
) -> AuthoredToolHandler:
    """
    Bind one authored tool definition to its runtime handler.

    Why this exists:
    - registry metadata alone is not callable; the runtime still needs one async
      handler that validates payloads, builds `ToolContext`, and coerces return
      values into `ToolInvocationResult`

    How to use it:
    - call while building the runtime handler map for one authored toolset

    Example:
    - `handler = _bind_tool_handler(authored_tool, runtime)`
    """

    async def handle(request: ToolInvocationRequest) -> ToolInvocationResult:
        from .api import ToolContext

        # Validate runtime payloads against the tool schema before calling the
        # authored Python function. This keeps tool handler code simple and
        # gives one consistent validation path for all authored tools.
        payload_model = authored_tool.args_schema.model_validate(request.payload)
        payload = payload_model.model_dump()
        context = ToolContext(runtime)
        try:
            value = authored_tool.handler(context, **payload)
            if inspect.isawaitable(value):
                value = await cast(Awaitable[object], value)
            return _coerce_tool_return(
                tool_ref=request.tool_ref,
                value=value,
                context=context,
                success_message=authored_tool.success_message,
            )
        except Exception as exc:
            # Last-resort safety net: any unhandled exception from authored
            # tool code (or from SDK helpers like ctx.publish_bytes,
            # ctx.read_resource, ctx.extract_structured) is caught here and
            # returned as a structured error result instead of crashing the
            # ReAct loop with a raw traceback.
            logger.exception(
                "Authored tool '%s' raised an unhandled exception", request.tool_ref
            )
            return ToolInvocationResult(
                tool_ref=request.tool_ref,
                blocks=_build_blocks(
                    text=f"Tool '{request.tool_ref}' failed: {exc}",
                    data=None,
                ),
                is_error=True,
            )

    return handle


def _coerce_tool_return(
    *,
    tool_ref: str,
    value: object,
    context: "ToolContext",
    success_message: str | None,
) -> ToolInvocationResult:
    """
    Normalize one authored tool return value to `ToolInvocationResult`.

    Why this exists:
    - authored tools should be able to return a small, explicit set of
      strongly-typed values instead of constructing `ToolInvocationResult`
      manually every time
    - this keeps the authoring SDK predictable and avoids weak fallback
      conversions

    How to use it:
    - call after invoking one authored tool handler
    - accepted return shapes are intentionally limited to:
      `ToolOutput`, `PublishedArtifact`, `BaseModel`, `str`, or `None`

    Example:
    - `result = _coerce_tool_return(tool_ref="knowledge.search", value=value, context=context, success_message=None)`
    """
    from .api import ToolOutput

    # Preserve sources collected through nested tool calls so that authored
    # tools can return a simple text/json result without manually re-threading
    # sources every time.
    collected_sources = context._collected_sources()

    if isinstance(value, ToolOutput):
        return ToolInvocationResult(
            tool_ref=tool_ref,
            blocks=_build_blocks(text=value.text, data=value.data),
            ui_parts=value.ui_parts,
            sources=value.sources or collected_sources,
            is_error=value.is_error,
        )

    if isinstance(value, PublishedArtifact):
        # Common business case: the tool produced a file and the runtime should
        # surface it as a downloadable link plus a short success message.
        text = success_message or f"Generated {value.file_name}."
        return ToolInvocationResult(
            tool_ref=tool_ref,
            blocks=_build_blocks(text=text, data=None),
            ui_parts=(value.to_link_part(),),
            sources=collected_sources,
        )

    if isinstance(value, BaseModel):
        # Pydantic models are treated as structured JSON output so authors can
        # return domain models directly from extraction-style tools.
        return ToolInvocationResult(
            tool_ref=tool_ref,
            blocks=_build_blocks(
                text=success_message,
                data=value.model_dump(),
            ),
            sources=collected_sources,
        )

    if isinstance(value, str):
        # Simple text is the normal authored-tool success path.
        return ToolInvocationResult(
            tool_ref=tool_ref,
            blocks=_build_blocks(text=value, data=None),
            sources=collected_sources,
        )

    if value is None:
        # Returning None means "success with optional static success_message".
        return ToolInvocationResult(
            tool_ref=tool_ref,
            blocks=_build_blocks(text=success_message, data=None),
            sources=collected_sources,
        )

    raise TypeError(
        "Authored tools must return one of: ToolOutput, PublishedArtifact, "
        "a Pydantic model, str, or None."
    )


def _build_blocks(
    *, text: str | None, data: dict[str, object] | None
) -> tuple[ToolContentBlock, ...]:
    """
    Build the content block tuple for one normalized tool result.

    Why this exists:
    - authored tool return coercion should construct Fred tool blocks in one
      place instead of duplicating TEXT/JSON branching

    How to use it:
    - pass optional text and optional JSON data

    Example:
    - `blocks = _build_blocks(text="Done", data={"count": 3})`
    """
    blocks: list[ToolContentBlock] = []
    if text:
        blocks.append(ToolContentBlock(kind=ToolContentKind.TEXT, text=text))
    if data is not None:
        blocks.append(ToolContentBlock(kind=ToolContentKind.JSON, data=data))
    return tuple(blocks)


__all__ = [
    "_AUTHOR_TOOL_ATTR",
    "_AuthorTool",
    "ensure_toolset_registered",
    "normalize_tool",
]
