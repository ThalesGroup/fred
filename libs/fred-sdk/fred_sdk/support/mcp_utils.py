"""
MCP content normalization utilities.

Why this module exists:
- MCP tools return content as structured blocks: [{"type": "text", "text": "..."}]
- LangChain expects ToolMessage.content to be a plain string
- one normalization path prevents duplicated block-extraction logic in every runtime

How to use it:
- call normalize_mcp_content(content) on any raw MCP tool output before
  placing it into a ToolMessage
"""

from __future__ import annotations

from typing import Any


def normalize_mcp_content(content: Any) -> Any:
    """
    Normalize MCP tool content blocks to a plain string.

    MCP tools return content as: [{"type": "text", "text": "..."}]
    LangChain expects ToolMessage.content to be a string.

    This function extracts text from content blocks and joins them,
    or returns the original content if already a string.

    For tools with response_format='content_and_artifact', the content is a
    tuple (content, artifact). In this case, only the content part is normalized.
    """
    # Handle content_and_artifact tuple format: (content, artifact)
    if isinstance(content, tuple) and len(content) == 2:
        normalized_content = normalize_mcp_content(content[0])
        return (normalized_content, content[1])

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    texts.append(text)
        if texts:
            return "\n".join(texts)

    return content
