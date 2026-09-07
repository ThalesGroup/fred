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
Render v2 ReAct tool results to the plain text and artifact shapes used at runtime.

Why this module exists:
- keep result rendering policy out of `react_tool_binding.py`
- make it obvious how Fred turns typed tool results into the strings returned to
  LangChain and the artifacts preserved for runtime events

How to use:
- import these helpers when wrapping one Fred tool port or one runtime-provider
  tool result

Example:
- `content = render_tool_result(result)`
"""

from __future__ import annotations

import json

from fred_sdk.contracts.context import (
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)

GENERIC_TOOL_FAILURE_MESSAGE = (
    "This step failed unexpectedly and could not be completed."
)


def render_tool_result(result: ToolInvocationResult) -> str:
    """
    Render one Fred tool result as text for LangChain tool return content.

    Why this exists:
    - Fred tools return typed content blocks, while LangChain tools need string content
    - one renderer keeps the text/json fallback policy stable across all tool bindings

    How to use:
    - pass the `ToolInvocationResult` returned by a Fred port

    Example:
    - `return render_tool_result(result)`
    """

    rendered_blocks: list[str] = []
    for block in result.blocks:
        if block.kind == ToolContentKind.TEXT and block.text is not None:
            rendered_blocks.append(block.text)
            continue
        if block.kind == ToolContentKind.JSON and block.data is not None:
            rendered_blocks.append(json.dumps(block.data, ensure_ascii=False, indent=2))
            continue
        rendered_blocks.append(_render_fallback_tool_block(block))

    if not rendered_blocks:
        rendered_blocks.append("")

    if result.is_error:
        return "Tool error:\n" + "\n".join(rendered_blocks)
    return "\n".join(rendered_blocks)


def stringify_tool_output(value: object) -> str:
    """
    Render one runtime-provider tool result to plain text.

    Why this exists:
    - runtime provider tools can return strings, dicts, block-like lists, or simple
      objects
    - provider-tool wrappers should normalize those values without importing the full
      LangChain message adapter layer

    How to use:
    - pass the raw provider tool result or one tuple element from `(content, artifact)`

    Example:
    - `stringify_tool_output(raw_result)`
    """

    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, indent=2)
    if isinstance(value, list):
        rendered_parts: list[str] = []
        for item in value:
            if isinstance(item, dict) and "text" in item:
                rendered_parts.append(str(item["text"]))
            else:
                rendered_parts.append(str(item))
        return "\n".join(part for part in rendered_parts if part)
    return str(value)


def normalize_runtime_provider_artifact(
    artifact: object,
) -> ToolInvocationResult | None:
    """Normalize a provider artifact and remove provider-controlled error detail.
    Error blocks, sources, and UI parts never cross this trust boundary."""

    if artifact is None:
        return None
    result = (
        artifact
        if isinstance(artifact, ToolInvocationResult)
        else ToolInvocationResult.model_validate(artifact)
    )
    if not result.is_error:
        return result
    return ToolInvocationResult(
        tool_ref=result.tool_ref,
        blocks=(
            ToolContentBlock(
                kind=ToolContentKind.TEXT,
                text=GENERIC_TOOL_FAILURE_MESSAGE,
            ),
        ),
        is_error=True,
    )


def _render_fallback_tool_block(block: ToolContentBlock) -> str:
    """
    Render one tool content block that was not handled by the main text/json branches.

    Why this exists:
    - Fred tool results are block-based and should degrade gracefully when a block
      carries only one optional field

    How to use:
    - call only from `render_tool_result(...)`

    Example:
    - `_render_fallback_tool_block(block)`
    """

    if block.text is not None:
        return block.text
    if block.data is not None:
        return json.dumps(block.data, ensure_ascii=False, indent=2)
    return ""
