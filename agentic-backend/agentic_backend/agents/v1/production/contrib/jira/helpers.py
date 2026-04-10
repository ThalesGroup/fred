"""Helper functions for Jira agent."""

import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)


def check_batch_conflict(runtime: Any, tool_name: str) -> str | None:
    """Check if *tool_name* was called in the same AI message as a conflicting tool.

    Returns an error message string if there is a conflict, ``None`` otherwise.
    Tools listed in ``batch_conflicts`` produce state that isn't visible to
    sibling tool calls in the same LangGraph step, so we ask the LLM to retry
    the dependent tool on the next turn.
    """
    batch_conflicts: dict[str, set[str]] = {
        "generate_user_stories": {"generate_requirements"},
        "generate_tests": {"generate_user_stories"},
    }

    conflicts = batch_conflicts.get(tool_name)
    if not conflicts:
        return None

    messages = runtime.state.get("messages") or []
    last_ai = next(
        (m for m in reversed(messages) if getattr(m, "type", None) == "ai"),
        None,
    )
    if last_ai is None:
        return None

    batch_tools = {tc.get("name") for tc in (getattr(last_ai, "tool_calls", []) or [])}
    found = conflicts & batch_tools
    if not found:
        return None

    logger.warning(
        "[JiraAgent] Batch conflict: %s called alongside %s — deferring",
        tool_name,
        found,
    )
    return (
        f"⚠️ {tool_name} a été appelé dans le même message que {', '.join(found)}. "
        f"Les données produites par {', '.join(found)} ne sont pas encore disponibles. "
        f"Appelle {tool_name}() seul dans ton prochain message."
    )


T = TypeVar("T", bound=BaseModel)


def ensure_pydantic_model(response: Any, model_class: type[T]) -> T:
    """Return response as a Pydantic model instance.

    LangChain's with_structured_output(method="json_schema") occasionally
    returns a raw dict instead of the model instance. This helper normalises
    the result so callers always get the expected type.
    """
    if isinstance(response, model_class):
        return response
    return model_class.model_validate(response)


def get_max_id_number(items: list[dict], pattern: str) -> int:
    """Extract the maximum numeric suffix from item IDs matching a regex pattern.

    Args:
        items: List of dicts with an "id" key.
        pattern: Regex with one capturing group for the number (e.g. r"US-(\\d+)").

    Returns:
        The highest number found, or 0 if none match.
    """
    max_num = 0
    for item in items:
        match = re.search(pattern, item.get("id", ""))
        if match:
            max_num = max(max_num, int(match.group(1)))
    return max_num


def get_next_user_story_id(state: dict) -> str:
    """Generate next US-XX ID based on existing stories."""
    existing_stories = state.get("user_stories") or []
    max_num = get_max_id_number(existing_stories, r"US-(\d+)")
    return f"US-{max_num + 1:02d}"


def get_next_test_id(state: dict) -> str:
    """Generate next SC-XX ID based on existing tests."""
    existing_tests = state.get("tests") or []
    max_num = get_max_id_number(existing_tests, r"SC-(\d+)")
    return f"SC-{max_num + 1:02d}"


def get_next_requirement_id(state: dict, req_type: str) -> str:
    """Generate next EX-FON-XX or EX-NFON-XX ID based on existing requirements."""
    existing_reqs = state.get("requirements") or []
    prefix = "EX-FON-" if req_type == "fonctionnelle" else "EX-NFON-"
    max_num = get_max_id_number(
        [r for r in existing_reqs if r.get("id", "").startswith(prefix)],
        r"-(\d+)$",
    )
    return f"{prefix}{max_num + 1:02d}"
