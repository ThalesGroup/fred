"""Helper functions for Jira agent."""

import re


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
