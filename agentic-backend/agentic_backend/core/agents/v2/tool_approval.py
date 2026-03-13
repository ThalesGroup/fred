from __future__ import annotations

"""
Typed tool-approval heuristics for the v2 ReAct runtime.

Why this file exists:
- the v2 SDK should own its approval semantics instead of importing them from
  the legacy agent layer
- developers need one obvious place to understand how generic tool approval is
  decided before any business-specific policy is added
- the policy remains simple on purpose: explicit tool names win, then a small
  set of read-only and mutating prefixes acts as the default heuristic
"""

READ_ONLY_TOOL_PREFIXES: tuple[str, ...] = (
    "get_",
    "list_",
    "search_",
    "find_",
    "track_",
    "quote_",
    "validate_",
    "estimate_",
    "seed_demo_",
    "read_",
    "describe_",
    "github_",
    "web_",
)

MUTATING_TOOL_PREFIXES: tuple[str, ...] = (
    "create_",
    "update_",
    "delete_",
    "remove_",
    "write_",
    "send_",
    "notify_",
    "reroute_",
    "reschedule_",
    "open_",
    "execute_",
    "run_",
    "purge_",
    "revectorize_",
    "build_",
    "drop_",
    "cancel_",
)


def requires_tool_approval(
    tool_name: str,
    *,
    approval_enabled: bool,
    exact_required_tools: set[str] | None = None,
) -> bool:
    """
    Decide whether a tool call should pause for human approval.

    Rules:
    - if approval is disabled, nothing pauses
    - exact tool names configured by the developer always require approval
    - obvious read-only tools do not require approval
    - obvious mutating tools do require approval
    - unknown names default to no approval until Fred introduces richer tool metadata
    """

    if not approval_enabled:
        return False

    exact = exact_required_tools or set()
    if tool_name in exact:
        return True

    if tool_name.startswith(READ_ONLY_TOOL_PREFIXES):
        return False

    if tool_name.startswith(MUTATING_TOOL_PREFIXES):
        return True

    return False
