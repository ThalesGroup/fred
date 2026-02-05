"""Helper functions for Jira agent."""

import re


def get_next_user_story_id(state: dict) -> str:
    """Generate next US-XX ID based on existing stories and titles."""
    existing_stories = state.get("user_stories") or []
    existing_titles = state.get("user_story_titles") or []
    all_ids = [s.get("id", "") for s in existing_stories + existing_titles]

    max_num = 0
    for id_str in all_ids:
        match = re.search(r"US-(\d+)", id_str)
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"US-{max_num + 1:02d}"


def get_next_test_id(state: dict) -> str:
    """Generate next SC-XX ID based on existing tests and titles."""
    existing_tests = state.get("tests") or []
    existing_titles = state.get("test_titles") or []
    all_ids = [t.get("id", "") for t in existing_tests + existing_titles]

    max_num = 0
    for id_str in all_ids:
        match = re.search(r"SC-(\d+)", id_str)
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"SC-{max_num + 1:02d}"


def get_next_requirement_id(state: dict, req_type: str) -> str:
    """Generate next EX-FON-XX or EX-NFON-XX ID based on existing requirements."""
    existing_reqs = state.get("requirements") or []
    prefix = "EX-FON-" if req_type == "fonctionnelle" else "EX-NFON-"

    max_num = 0
    for req in existing_reqs:
        id_str = req.get("id", "")
        if id_str.startswith(prefix):
            match = re.search(r"-(\d+)$", id_str)
            if match:
                max_num = max(max_num, int(match.group(1)))
    return f"{prefix}{max_num + 1:02d}"
