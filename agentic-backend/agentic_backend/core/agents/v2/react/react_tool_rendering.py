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

from ..contracts.context import ToolContentBlock, ToolContentKind, ToolInvocationResult


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
    """
    Parse one optional runtime-provider artifact into the Fred tool result model.

    Why this exists:
    - runtime provider tools can return `(content, artifact)` tuples
    - provider-tool wrappers still want one typed Fred artifact shape

    How to use:
    - pass the second element of a provider-tool tuple result

    Example:
    - `artifact = normalize_runtime_provider_artifact(raw_result[1])`
    """

    if artifact is None:
        return None
    if isinstance(artifact, ToolInvocationResult):
        return artifact
    return ToolInvocationResult.model_validate(artifact)


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
