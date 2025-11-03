import logging
from typing import (
    Sequence,
)

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    ToolMessage,
)

logger = logging.getLogger(__name__)


def log_agent_message_summary(
    messages: Sequence[AnyMessage], label: str = "Messages"
) -> None:
    """
    Log a concise summary of message sequence for debugging purposes.

    Each line shows:
        [index] role/type | content preview | tool_call_id(s)
    """
    if not messages:
        logger.info(f"[AGENTS] {label}: (empty)")
        return

    logger.info(f"[AGENTS] ---- Restored history {label} messages={len(messages)} ----")
    for i, msg in enumerate(messages):
        # Determine message role/type
        role = (
            getattr(msg, "type", None)
            or getattr(msg, "role", None)
            or type(msg).__name__
        )
        content = getattr(msg, "content", "")
        preview = ""

        # Short preview for readability
        if isinstance(content, str):
            preview = content.strip().replace("\n", " ")
            if len(preview) > 60:
                preview = preview[:57] + "..."
        elif isinstance(content, list):
            preview = f"[list x{len(content)}]"
        elif isinstance(content, dict):
            preview = f"[dict keys={list(content.keys())}]"

        # Tool metadata
        extra = ""
        if isinstance(msg, AIMessage):
            tool_calls = getattr(msg, "tool_calls", None)
            if tool_calls:
                ids = [
                    tc.get("id") or tc.get("name") or "<no-id>"
                    for tc in tool_calls
                    if isinstance(tc, dict)
                ]
                extra = f" tool_calls={ids}"
        elif isinstance(msg, ToolMessage):
            tcid = getattr(msg, "tool_call_id", None)
            if tcid:
                extra = f" tool_call_id={tcid}"

        logger.info(f"[AGENTS] [{i:02d}] {role:<10} | {preview}{extra}")

    logger.info(f"[AGENTS] ---- End restored summary {label} ----")
