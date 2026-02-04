"""Helper functions for Jira agent."""

import re


def get_next_user_story_id(state: dict) -> str:
    """Generate next US-XX ID based on existing stories."""
    existing_stories = state.get("user_stories") or []

    max_num = 0
    for story in existing_stories:
        match = re.search(r"US-(\d+)", story.get("id", ""))
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"US-{max_num + 1:02d}"


def get_next_test_id(state: dict) -> str:
    """Generate next SC-XX ID based on existing tests."""
    existing_tests = state.get("tests") or []
    all_ids = [t.get("id", "") for t in existing_tests]

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
