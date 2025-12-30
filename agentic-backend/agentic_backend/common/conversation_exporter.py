"""
Utilities for exporting and formatting conversation histories.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentic_backend.core.agents.agent_flow import AgentFlow

logger = logging.getLogger(__name__)


async def export_conversation_to_asset(
    agent: AgentFlow,
    conversation_text: str,
    filename: str | None = None,
    asset_key_prefix: str | None = None,
) -> tuple[str, str]:
    """
    Export conversation text to user assets and return download URL.

    Args:
        agent: The agent instance (must have upload_user_asset and get_asset_download_url)
        conversation_text: The formatted conversation text to export
        filename: Optional filename (default: "conversation.txt")
        asset_key_prefix: Optional prefix for asset key (default: "conversation")

    Returns:
        tuple[str, str]: A tuple containing (download_url, asset_key)

    Raises:
        ValueError: If conversation text is empty
        AttributeError: If asset client is not initialized
    """
    if not conversation_text or len(conversation_text.strip()) == 0:
        raise ValueError("Conversation text cannot be empty")

    filename = filename or "conversation.txt"
    asset_key_prefix = asset_key_prefix or "conversation"

    # Convert to bytes
    file_content = conversation_text.encode("utf-8")
    logger.info(f"Exporting conversation: {len(file_content)} bytes")

    # Add timestamp to make asset key unique
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name, ext = (
        filename.rsplit(".", 1) if "." in filename else (filename, "")
    )
    unique_filename = (
        f"{name}_{timestamp}.{ext}" if ext else f"{filename}_{timestamp}"
    )
    unique_asset_key = f"{asset_key_prefix}_{timestamp}"

    logger.info(
        f"Using unique asset key: {unique_asset_key}, "
        f"filename: {unique_filename}"
    )

    try:
        # Upload the asset to user storage
        upload_result = await agent.upload_user_asset(
            key=unique_asset_key,
            file_content=file_content,
            filename=unique_filename,
            content_type="text/plain",
        )

        logger.info(
            f"Conversation exported successfully. Key: {upload_result.key}, "
            f"Size: {upload_result.size}"
        )

        # Construct the download URL
        download_url = agent.get_asset_download_url(
            asset_key=upload_result.key, scope="user"
        )

        return download_url, upload_result.key
    except AttributeError as e:
        logger.error(
            f"Asset client not initialized: {e}. "
            f"Ensure async_init() is called properly."
        )
        raise


def _extract_message_content(msg: Any) -> str:
    """
    Extract content from a message, checking multiple possible locations.
    
    Args:
        msg: A message object
        
    Returns:
        str: The extracted content, or empty string if none found
    """
    # First try the direct content attribute
    content = getattr(msg, "content", "")
    
    # If content is empty, try to get it from response_metadata
    if not content or content == "":
        metadata = getattr(msg, "response_metadata", {})
        if metadata:
            # Try 'thought' field first (for thought messages)
            content = metadata.get("thought", "")
            
            # If still empty, check for tool_calls
            if not content:
                tool_calls = getattr(msg, "tool_calls", None)
                if tool_calls:
                    # Format tool calls
                    tool_parts = []
                    for tc in tool_calls:
                        tool_name = tc.get("name", "unknown") if isinstance(tc, dict) else getattr(tc, "name", "unknown")
                        tool_args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                        tool_parts.append(
                            f"Tool: {tool_name}\n"
                            f"Args: {tool_args}"
                        )
                    content = "\n".join(tool_parts)
    
    return content


def format_conversation_from_messages(
    messages: list[Any],
    question: str | None = None,
    generation: Any | None = None,
    sources: list[Any] | None = None,
) -> str:
    """
    Format conversation history into readable text.

    Args:
        messages: List of message objects with 'type' and 'content' attributes
        question: Optional original question
        generation: Optional generated response
        sources: Optional list of source documents

    Returns:
        str: Formatted conversation text
    """
    formatted_lines: list[str] = [
        "=" * 80,
        "CONVERSATION HISTORY",
        "=" * 80,
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 80,
        "",
    ]

    # Add original question if provided (and not already in messages)
    question_added = False
    if question:
        formatted_lines.extend(
            [
                "[1] 👤 User",
                "-" * 40,
                question,
                "",
            ]
        )
        question_added = True

    # Format messages
    if messages:
        msg_counter = 2 if question_added else 1
        for msg in messages:
            msg_type = getattr(msg, "type", "unknown").upper()

            # Skip system messages
            if msg_type == "SYSTEM":
                continue

            # Format role
            if msg_type in ("HUMAN", "USER"):
                role_label = "👤 User"
            elif msg_type in ("AI", "ASSISTANT"):
                role_label = "🤖 Assistant"
            elif msg_type == "TOOL":
                role_label = "🔧 Tool"
            else:
                role_label = f"📌 {msg_type}"

            # Extract content using the helper function
            content = _extract_message_content(msg)
            
            # Skip if no content found
            if not content or content == "":
                continue

            formatted_lines.extend(
                [
                    f"[{msg_counter}] {role_label}",
                    "-" * 40,
                    str(content),
                    "",
                ]
            )
            msg_counter += 1

    # Add generated response if provided and not already in messages
    if generation and not messages:
        formatted_lines.extend(
            [
                "[2] 🤖 Assistant",
                "-" * 40,
                getattr(generation, "content", ""),
                "",
            ]
        )

    # Add sources if available
    if sources:
        formatted_lines.extend(
            [
                "",
                "=" * 80,
                "SOURCES USED",
                "=" * 80,
                "",
            ]
        )
        for i, doc in enumerate(sources, 1):
            file_name = getattr(doc, "file_name", None) or getattr(
                doc, "title", "Unknown"
            )
            page = getattr(doc, "page", "n/a")
            content = getattr(doc, "content", "")[:200]
            formatted_lines.extend(
                [
                    f"Source {i}:",
                    f"  File: {file_name}",
                    f"  Page: {page}",
                    f"  Content: {content}...",
                    "",
                ]
            )

    # Check if we have actual content
    if len(formatted_lines) <= 6:  # Only headers, no actual content
        return "No conversation history available."

    formatted_lines.extend(
        [
            "=" * 80,
            "END OF CONVERSATION",
            "=" * 80,
        ]
    )

    return "\n".join(formatted_lines)