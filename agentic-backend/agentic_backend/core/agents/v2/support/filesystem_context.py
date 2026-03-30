"""
Filesystem browsing context derived from prior tool traffic.

Use this helper module when a ReAct-style runtime exposes filesystem tools and
needs deterministic path continuation across turns. The goal is to keep
filesystem navigation grounded in tool history instead of relying only on
natural-language memory.
"""

from __future__ import annotations

import json
import posixpath
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

_FILESYSTEM_TOOL_NAMES = frozenset(
    {
        "ls",
        "stat_file_or_directory",
        "read_file",
        "write_file",
        "delete_file",
        "edit_file",
        "glob",
        "grep",
        "mkdir",
    }
)


@dataclass(frozen=True, slots=True)
class FilesystemBrowsingContext:
    """
    Deterministic browsing state inferred from filesystem tool history.

    Why this exists:
    - short follow-ups like `CIR` or `ouvre DATA` are ambiguous without a base path
    - filesystem agents should continue browsing from the last real tool-backed location

    How to use:
    - build the context from prior messages plus the currently available tool names
    - inject the rendered state into the next model call when filesystem tools are present

    Example:
    - after `ls /corpus` returned `CIR` and `DATA`, a user follow-up `CIR`
      resolves with:
      - `current_base_path=/corpus`
      - `last_selected_entry=CIR`
      - `last_selected_path=/corpus/CIR`
    """

    current_base_path: str
    last_listed_directory: str | None
    last_selected_entry: str | None
    last_selected_path: str | None
    visible_entries: tuple[str, ...]
    latest_user_selected_visible_entry: bool


@dataclass(frozen=True, slots=True)
class _PendingFilesystemToolCall:
    tool_name: str
    path: str


def supports_filesystem_browsing_context(tool_names: set[str] | frozenset[str]) -> bool:
    """
    Tell the runtime whether filesystem browsing state is worth computing.

    Why this exists:
    - only filesystem-capable agents need path continuation state
    - this keeps non-filesystem ReAct prompts unchanged

    How to use:
    - pass the set of bound runtime tool names for the current agent

    Example:
    - `supports_filesystem_browsing_context({"ls", "read_file"})`
    """

    return any(name in _FILESYSTEM_TOOL_NAMES for name in tool_names)


def build_filesystem_browsing_context(
    messages: Sequence[object],
    *,
    available_tool_names: set[str] | frozenset[str],
) -> FilesystemBrowsingContext | None:
    """
    Derive one browsing context from prior filesystem tool calls and results.

    Why this exists:
    - ReAct message history contains the raw facts needed to continue browsing
    - turning those facts into one explicit context object makes follow-up turns reliable

    How to use:
    - pass chronological conversation messages plus the currently available tool names
    - use the returned context to guide relative path resolution in the next model call

    Example:
    - `build_filesystem_browsing_context(messages, available_tool_names={"ls"})`
    """

    if not supports_filesystem_browsing_context(available_tool_names):
        return None

    pending_calls: dict[str, _PendingFilesystemToolCall] = {}
    current_base_path: str | None = None
    last_listed_directory: str | None = None
    last_selected_entry: str | None = None
    last_selected_path: str | None = None
    visible_entries: tuple[str, ...] = ()
    latest_user_selected_visible_entry = False

    for message in messages:
        if isinstance(message, AIMessage):
            for tool_call in getattr(message, "tool_calls", ()) or ():
                tool_name = str(tool_call.get("name") or "").strip()
                if tool_name not in _FILESYSTEM_TOOL_NAMES:
                    continue
                tool_call_id = str(tool_call.get("id") or "").strip()
                if not tool_call_id:
                    continue
                tool_args = tool_call.get("args") or {}
                if not isinstance(tool_args, dict):
                    continue
                tool_path = _filesystem_tool_path(
                    tool_name,
                    cast(dict[str, object], tool_args),
                )
                if tool_path is None:
                    continue
                pending_calls[tool_call_id] = _PendingFilesystemToolCall(
                    tool_name=tool_name,
                    path=tool_path,
                )
            continue

        if not isinstance(message, ToolMessage):
            continue
        tool_call_id = getattr(message, "tool_call_id", None)
        if not isinstance(tool_call_id, str):
            continue
        pending = pending_calls.get(tool_call_id)
        if pending is None or _is_tool_error_message(message):
            continue

        if pending.tool_name == "ls":
            last_listed_directory = pending.path
            current_base_path = pending.path
            visible_entries = _parse_listing_entries(_message_text(message))
            selected_name = _nested_selection_name(pending.path)
            if selected_name is not None:
                last_selected_entry = selected_name
                last_selected_path = pending.path
            continue

        if pending.tool_name in {
            "stat_file_or_directory",
            "read_file",
            "write_file",
            "delete_file",
            "edit_file",
        }:
            current_base_path = _parent_directory(pending.path)
            last_selected_entry = _entry_name(pending.path)
            last_selected_path = pending.path
            continue

        if pending.tool_name in {"glob", "grep"}:
            current_base_path = pending.path
            continue

        if pending.tool_name == "mkdir":
            current_base_path = pending.path
            last_selected_entry = _entry_name(pending.path)
            last_selected_path = pending.path

    latest_user_text = _latest_human_text(messages)
    if (
        latest_user_text is not None
        and last_listed_directory is not None
        and visible_entries
    ):
        selected_entry = _resolve_visible_entry_selection(
            latest_user_text,
            visible_entries,
        )
        if selected_entry is not None:
            last_selected_entry = selected_entry
            last_selected_path = _join_virtual_child(
                last_listed_directory,
                selected_entry,
            )
            current_base_path = last_listed_directory
            latest_user_selected_visible_entry = True

    if current_base_path is None:
        return None

    return FilesystemBrowsingContext(
        current_base_path=current_base_path,
        last_listed_directory=last_listed_directory,
        last_selected_entry=last_selected_entry,
        last_selected_path=last_selected_path,
        visible_entries=visible_entries,
        latest_user_selected_visible_entry=latest_user_selected_visible_entry,
    )


def render_filesystem_browsing_context(
    messages: Sequence[object],
    *,
    available_tool_names: set[str] | frozenset[str],
) -> str:
    """
    Render filesystem browsing context as prompt-ready guardrail text.

    Why this exists:
    - the model needs a small explicit reminder of the active filesystem context
    - rendering one stable suffix keeps the runtime deterministic and easy to test

    How to use:
    - call before each model step when filesystem tools are available
    - append the returned string to the base system prompt only when non-empty

    Example:
    - `prompt = base_prompt + render_filesystem_browsing_context(messages, available_tool_names=tool_names)`
    """

    context = build_filesystem_browsing_context(
        messages,
        available_tool_names=available_tool_names,
    )
    if context is None:
        return ""

    lines = [
        "",
        "Filesystem browsing context:",
        f"- Current base path: {context.current_base_path}",
    ]
    if context.last_listed_directory is not None:
        lines.append(f"- Last listed directory: {context.last_listed_directory}")
    if context.last_selected_entry is not None:
        lines.append(f"- Last selected entry: {context.last_selected_entry}")
    if context.last_selected_path is not None:
        lines.append(f"- Resolved selected path: {context.last_selected_path}")
    if context.visible_entries and context.last_listed_directory is not None:
        preview = ", ".join(context.visible_entries[:12])
        lines.append(f"- Visible entries in {context.last_listed_directory}: {preview}")
    lines.extend(
        [
            "Filesystem resolution rules for this turn:",
            f"- Resolve short follow-up names relative to {context.current_base_path}.",
            "- When the user is clearly browsing files, prefer this active path context over defaulting to /workspace.",
        ]
    )
    return "\n".join(lines)


def rewrite_filesystem_tool_arguments(
    tool_name: str,
    tool_args: dict[str, object],
    *,
    messages: Sequence[object],
    available_tool_names: set[str] | frozenset[str],
) -> dict[str, object]:
    """
    Resolve one filesystem tool payload against the current browsing context.

    Why this exists:
    - plain ReAct memory is not enough to guarantee that short follow-ups become the
      right tool arguments
    - rewriting filesystem paths once in the runtime keeps plain ReAct and HITL
      behavior aligned

    How to use:
    - pass the pending filesystem tool call plus the chronological message history
    - use the returned payload for the actual tool execution

    Example:
    - after listing `/corpus`, a follow-up `CIR` can turn `{"path": "/"}` into
      `{"path": "/corpus/CIR"}`
    """

    if tool_name not in _FILESYSTEM_TOOL_NAMES:
        return tool_args

    context = build_filesystem_browsing_context(
        messages,
        available_tool_names=available_tool_names,
    )
    if context is None:
        return tool_args

    path_key = _filesystem_tool_path_key(tool_name, tool_args)
    if path_key is None:
        return tool_args

    rewritten = dict(tool_args)
    raw_path = rewritten.get(path_key)
    if isinstance(raw_path, str) and raw_path.strip():
        cleaned_path = _strip_wrapping_quotes(raw_path.strip())
        if cleaned_path and not cleaned_path.startswith("/"):
            rewritten[path_key] = _join_virtual_child(
                context.current_base_path,
                cleaned_path,
            )
            return rewritten
        normalized_path = _normalize_virtual_path(cleaned_path or raw_path)
        if (
            context.latest_user_selected_visible_entry
            and context.last_selected_path is not None
            and normalized_path in {"/", "/workspace", context.current_base_path}
        ):
            rewritten[path_key] = context.last_selected_path
            return rewritten
        return tool_args

    if (
        context.latest_user_selected_visible_entry
        and context.last_selected_path is not None
    ):
        rewritten[path_key] = context.last_selected_path
        return rewritten
    return tool_args


def _filesystem_tool_path(
    tool_name: str,
    tool_args: dict[str, object],
) -> str | None:
    """
    Extract the visible path argument used by one filesystem tool call.

    Why this exists:
    - different filesystem tools pass their target path under slightly different keys
    - the browsing context should normalize that difference once

    How to use:
    - pass one runtime tool name plus its decoded argument payload

    Example:
    - `_filesystem_tool_path("ls", {"path": "/corpus"})`
    """

    raw_path = tool_args.get("path")
    if tool_name == "grep" and raw_path is None:
        raw_path = tool_args.get("prefix")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    return _normalize_virtual_path(raw_path)


def _filesystem_tool_path_key(
    tool_name: str,
    tool_args: dict[str, object],
) -> str | None:
    """
    Return the argument key that carries the visible path for one filesystem tool.

    Why this exists:
    - rewriting tool payloads must preserve each tool's expected argument name
    - grep uses `prefix` while most filesystem tools use `path`

    How to use:
    - pass one tool name and its decoded argument payload

    Example:
    - `_filesystem_tool_path_key("grep", {"prefix": "/corpus"})`
    """

    if tool_name == "grep" and "prefix" in tool_args and "path" not in tool_args:
        return "prefix"
    if "path" in tool_args:
        return "path"
    if tool_name in {
        "ls",
        "stat_file_or_directory",
        "read_file",
        "write_file",
        "delete_file",
        "edit_file",
        "glob",
        "mkdir",
    }:
        return "path"
    if tool_name == "grep":
        return "prefix"
    return None


def _normalize_virtual_path(path: str) -> str:
    """
    Normalize one visible virtual filesystem path to absolute POSIX form.

    Why this exists:
    - browsing state should compare paths in one stable format

    How to use:
    - pass any visible path string, absolute or relative

    Example:
    - `_normalize_virtual_path("corpus/CIR")`
    """

    normalized = posixpath.normpath(path if path.startswith("/") else f"/{path}")
    return normalized if normalized.startswith("/") else f"/{normalized}"


def _strip_wrapping_quotes(value: str) -> str:
    """
    Remove one layer of matching wrapping quotes from a short user-provided path.

    Why this exists:
    - models sometimes pass selections such as `"CIR"` instead of `CIR`
    - path resolution should treat those short quoted selections as the same entry

    How to use:
    - pass one raw path-like string before filesystem normalization

    Example:
    - `_strip_wrapping_quotes('"CIR"')`
    """

    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _join_virtual_child(base_path: str, child_name: str) -> str:
    """
    Join one visible child entry name under a visible base path.

    Why this exists:
    - follow-up selection resolution needs one deterministic visible child path

    How to use:
    - pass the listed directory plus the selected entry name

    Example:
    - `_join_virtual_child("/corpus", "CIR")`
    """

    if base_path == "/":
        return _normalize_virtual_path(child_name)
    return _normalize_virtual_path(f"{base_path.rstrip('/')}/{child_name.lstrip('/')}")


def _parent_directory(path: str) -> str:
    """
    Return the visible parent directory for one visible path.

    Why this exists:
    - file-oriented operations should keep browsing anchored to the containing folder

    How to use:
    - pass one normalized visible path

    Example:
    - `_parent_directory("/workspace/report.txt")`
    """

    parent = posixpath.dirname(path.rstrip("/"))
    return parent or "/"


def _entry_name(path: str) -> str | None:
    """
    Return the last visible path segment when one exists.

    Why this exists:
    - the browsing context needs a stable selected entry label

    How to use:
    - pass one normalized visible path

    Example:
    - `_entry_name("/corpus/CIR")`
    """

    cleaned = path.rstrip("/")
    if not cleaned or cleaned == "/":
        return None
    return posixpath.basename(cleaned) or None


def _nested_selection_name(path: str) -> str | None:
    """
    Return the selected child name when the path is nested below the root.

    Why this exists:
    - listing `/corpus/CIR` implies the user already selected `CIR`
    - listing `/corpus` alone should not pretend `corpus` is the selected entry

    How to use:
    - pass one normalized visible path

    Example:
    - `_nested_selection_name("/corpus/CIR")`
    """

    cleaned = path.strip("/")
    if not cleaned or "/" not in cleaned:
        return None
    return posixpath.basename(cleaned) or None


def _message_text(message: ToolMessage | HumanMessage) -> str:
    """
    Convert one LangChain human/tool message content to plain text.

    Why this exists:
    - browsing helpers should work with string and block-style message content

    How to use:
    - pass one `HumanMessage` or `ToolMessage`

    Example:
    - `_message_text(HumanMessage(content="show /corpus"))`
    """

    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        rendered_parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                rendered_parts.append(str(item["text"]))
            else:
                rendered_parts.append(str(item))
        return "\n".join(part for part in rendered_parts if part)
    return str(content)


def _is_tool_error_message(message: ToolMessage) -> bool:
    """
    Tell whether one tool result message represents an error.

    Why this exists:
    - failed tool calls should not update browsing context

    How to use:
    - pass one tool result message

    Example:
    - `_is_tool_error_message(tool_message)`
    """

    return _message_text(message).lstrip().startswith("Tool error:")


def _parse_listing_entries(content: str) -> tuple[str, ...]:
    """
    Parse direct-entry names from one `ls` tool result payload.

    Why this exists:
    - follow-up selection only works when the runtime remembers the names just listed

    How to use:
    - pass the raw tool message content returned by `ls`

    Example:
    - `_parse_listing_entries('[{\"path\": \"CIR\"}]')`
    """

    try:
        payload = json.loads(content)
    except Exception:
        return ()
    if not isinstance(payload, list):
        return ()

    names: list[str] = []
    seen: set[str] = set()
    for item in payload:
        candidate: str | None = None
        if isinstance(item, dict):
            raw_path = item.get("path")
            if isinstance(raw_path, str) and raw_path.strip():
                candidate = raw_path.strip()
        elif isinstance(item, str) and item.strip():
            candidate = item.strip()
        if candidate is None or candidate in seen:
            continue
        seen.add(candidate)
        names.append(candidate)
    return tuple(names)


def _latest_human_text(messages: Sequence[object]) -> str | None:
    """
    Return the newest human utterance text from one message history.

    Why this exists:
    - short follow-up selection should resolve from the user's latest wording

    How to use:
    - pass chronological LangChain messages

    Example:
    - `_latest_human_text(messages)`
    """

    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            rendered = _message_text(message)
            return rendered.strip() or None
    return None


def _resolve_visible_entry_selection(
    user_text: str,
    visible_entries: tuple[str, ...],
) -> str | None:
    """
    Resolve one short human follow-up to a listed entry name.

    Why this exists:
    - natural follow-ups like `CIR` or `ouvre DATA` should map to a real listed child

    How to use:
    - pass the latest human text plus the direct entries from the last listing

    Example:
    - `_resolve_visible_entry_selection(\"le contenu de CIR stp\", (\"CIR\", \"DATA\"))`
    """

    if "/" in user_text:
        return None

    matches: list[str] = []
    lowered = user_text.casefold()
    for entry in visible_entries:
        pattern = re.compile(rf"(?<![\w/]){re.escape(entry.casefold())}(?![\w/])")
        if pattern.search(lowered):
            matches.append(entry)
    if len(matches) == 1:
        return matches[0]
    return None
