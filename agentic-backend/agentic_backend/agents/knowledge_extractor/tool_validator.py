"""
Clauded
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)


def create_tool_call_validator_middleware(tool_names: list[str]) -> Callable:
    """
    Creates a middleware function that detects failed tool calls and injects
    corrective feedback into the conversation.

    Args:
        tool_names: List of tool names to watch for (e.g., ['template_tool', 'validator_tool'])

    Returns:
        Middleware function that can be used with @after_model

    Usage:
        validator_middleware = create_tool_call_validator_middleware(
            ['template_tool', 'validator_tool']
        )

        @after_model
        def validate_tool_calls(state, runtime):
            return validator_middleware(state, runtime)
    """

    def validator_middleware(state: dict, runtime: Any) -> dict | None:
        """
        Detects failed tool calls and injects system feedback.
        """
        messages = state.get("messages", [])
        if not messages:
            return None

        last_message = messages[-1]

        # Only process AI messages
        if getattr(last_message, "type", "") != "ai":
            return None

        # Check for malformed tool calls (JSON as function name)
        tool_calls = getattr(last_message, "tool_calls", None)
        if tool_calls:
            malformed_calls = []
            for tc in tool_calls:
                tool_name = tc.get("name", "")
                # If the name starts with { or contains JSON-like structure, it's malformed
                if tool_name.startswith("{") or ('"' in tool_name and ":" in tool_name):
                    malformed_calls.append(tc)
                # Also check if name is not in our allowed tool names
                elif tool_name not in tool_names and not tool_name.startswith("search"):
                    # Might be using JSON as the name
                    if "{" in tool_name or len(tool_name) > 100:
                        malformed_calls.append(tc)

            if malformed_calls:
                logger.error(
                    f"🚨 Detected {len(malformed_calls)} malformed tool call(s) with JSON as function name!"
                )

                # Build error message
                error_parts = [
                    "❌ CRITICAL ERROR: Invalid Tool Call Structure",
                    "",
                    "You attempted to call a tool but used the JSON data as the function name.",
                    "This is completely incorrect and causes the API to reject the request.",
                    "",
                ]

                for tc in malformed_calls:
                    bad_name = tc.get("name", "")[:200]
                    error_parts.append("You tried to use this as a function name:")
                    error_parts.append(f"`{bad_name}...`")
                    error_parts.append("")

                error_parts.extend(
                    [
                        "📋 CORRECT FORMAT:",
                        f"1. Function name must be ONE of: {', '.join(tool_names)}",
                        "2. The JSON data goes in the 'arguments' field, NOT the 'name' field",
                        "",
                        "Example of CORRECT structure:",
                        "- name: 'template_tool'",
                        '- arguments: {"data": {...}}',
                        "",
                        "🔄 Please try again with the correct tool call structure.",
                    ]
                )

                error_message = "\n".join(error_parts)

                # Remove the malformed tool calls to prevent API error
                last_message.tool_calls = []

                # Inject corrective system message
                from langchain_core.messages import SystemMessage

                system_correction = SystemMessage(content=error_message)
                messages.append(system_correction)

                logger.info(
                    "✅ Removed malformed tool calls and injected corrective feedback"
                )

                return {"messages": messages}

        # If there are proper tool calls, all is good
        if getattr(last_message, "tool_calls", None):
            return None

        content = getattr(last_message, "content", "")
        if not isinstance(content, str):
            return None

        # Check for each tool name in the content
        detected_failures = []

        for tool_name in tool_names:
            # Pattern 1: tool_name followed by JSON
            pattern_with_json = (
                rf"({re.escape(tool_name)})\s*[\(:]*\s*(\{{[^}}]*\}}|\{{[\s\S]*?\}})"
            )
            matches_with_json = re.findall(
                pattern_with_json, content, re.IGNORECASE | re.MULTILINE
            )

            if matches_with_json:
                for match in matches_with_json:
                    detected_tool = match[0]
                    json_attempt = match[1]

                    # Try to parse the JSON to see if it's valid
                    try:
                        parsed_args = json.loads(json_attempt)
                        detected_failures.append(
                            {
                                "tool": detected_tool,
                                "args": parsed_args,
                                "raw": f"{detected_tool} {json_attempt}",
                            }
                        )
                    except json.JSONDecodeError:
                        detected_failures.append(
                            {
                                "tool": detected_tool,
                                "args": None,
                                "raw": f"{detected_tool} {json_attempt[:100]}...",
                            }
                        )

            # Pattern 2: tool_name mentioned alone (without proper tool call)
            # Only flag if it appears to be an attempt to call the tool, not just mentioned in conversation
            # Look for patterns like:
            # - "template_tool" at the end of a message
            # - "Now calling template_tool"
            # - "template_tool<newline>" or "template_tool."
            pattern_standalone = rf"\b({re.escape(tool_name)})\b\s*[.\n]?$"
            if re.search(pattern_standalone, content, re.IGNORECASE | re.MULTILINE):
                # Only flag it if it's not already captured in the JSON pattern
                already_found = any(
                    f["tool"].lower() == tool_name.lower() for f in detected_failures
                )
                if not already_found:
                    # Additional check: make sure it looks like an attempt to call, not just a mention
                    # (e.g., "I will use template_tool" vs just "template_tool")
                    context_pattern = (
                        rf"(?:now|calling|using|use)\s+{re.escape(tool_name)}\b"
                    )
                    is_explicit_attempt = re.search(
                        context_pattern, content, re.IGNORECASE
                    )
                    ends_with_tool = content.strip().endswith(tool_name)

                    if is_explicit_attempt or ends_with_tool:
                        detected_failures.append(
                            {
                                "tool": tool_name,
                                "args": None,
                                "raw": f"{tool_name} (no arguments provided)",
                            }
                        )

        if not detected_failures:
            return None

        # Log the detection
        logger.warning(
            f"🚨 Detected {len(detected_failures)} failed tool call(s) in text. "
            f"Injecting corrective feedback."
        )

        # Build a helpful error message
        error_parts = [
            "❌ ERROR: Tool Call Format Invalid",
            "",
            "You attempted to call a tool by writing its name as text. This is incorrect.",
            "",
        ]

        for failure in detected_failures:
            error_parts.append(f"You wrote: `{failure['raw']}`")

        error_parts.extend(
            [
                "",
                "📋 CORRECT FORMAT:",
                "To call tools, you MUST use the proper tool calling mechanism provided by your LLM interface.",
                "Do NOT write the tool name followed by JSON in your text response.",
                "",
                "The tool call should be structured as a tool_call object, not as text.",
                "",
                "🔄 Please try again using the proper tool calling format.",
            ]
        )

        # If we detected valid JSON, show what they tried to pass
        if detected_failures[0]["args"]:
            error_parts.extend(
                [
                    "",
                    "Note: I can see you wanted to pass these arguments:",
                    "```json",
                    f"{json.dumps(detected_failures[0]['args'], indent=2)[:500]}",
                    "```",
                    "Use these same arguments, but call the tool properly.",
                ]
            )

        error_message = "\n".join(error_parts)

        # Create a system message with the correction
        from langchain_core.messages import SystemMessage

        system_correction = SystemMessage(content=error_message)

        # Remove the failed tool call text from the AI message to keep it clean
        cleaned_content = content
        for failure in detected_failures:
            # Remove the failed attempt from content
            pattern = re.escape(failure["tool"]) + r"\s*[\(:]*\s*\{[^\}]*\}"
            cleaned_content = re.sub(pattern, "", cleaned_content, flags=re.IGNORECASE)

        cleaned_content = cleaned_content.strip()

        # Update the last message content to remove the failed attempt
        if cleaned_content:
            last_message.content = cleaned_content
        else:
            # If the entire message was just the failed tool call, set to empty
            # so the stream_transcoder will filter it out as an empty observation
            last_message.content = ""

        # Append the system correction to messages
        messages.append(system_correction)

        logger.info(
            f"✅ Injected corrective feedback for {len(detected_failures)} failed tool call(s). "
            f"Agent will see the error and can retry."
        )

        return {"messages": messages}

    return validator_middleware


def has_validation_error(messages: list) -> bool:
    """
    Check if the last messages contain a validation error from the validator middleware.

    Args:
        messages: List of messages to check

    Returns:
        True if there's a validation error, False otherwise
    """
    if not messages:
        return False

    # Check the last few messages for system error messages
    for msg in reversed(messages[-3:]):  # Check last 3 messages
        if getattr(msg, "type", "") == "system":
            content = getattr(msg, "content", "")
            if isinstance(content, str) and (
                "❌ ERROR: Tool Call Format Invalid" in content
                or "❌ CRITICAL ERROR: Invalid Tool Call Structure" in content
            ):
                return True

    return False
