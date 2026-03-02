from __future__ import annotations

import json
from collections.abc import Sequence
from importlib.resources import files


def load_packaged_json_object(
    *, package: str, path_parts: Sequence[str]
) -> dict[str, object]:
    """
    Load a packaged JSON object from an explicit package-relative path.

    Why this helper exists:
    - some agent resources are structured vocabularies or lexical defaults, not
      markdown prompts
    - agents should not open ad hoc filesystem paths directly
    - keeping a shared loader gives v2 one recognizable pattern for packaged
      non-code resources that may later become tunable
    """

    if not path_parts:
        raise ValueError("path_parts must contain at least one path segment.")

    resource_path = files(package)
    for part in path_parts:
        resource_path = resource_path.joinpath(part)

    try:
        payload = json.loads(resource_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Missing packaged JSON resource: {resource_path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid packaged JSON resource: {resource_path}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(
            f"Packaged JSON resource must contain an object at top level: {resource_path}"
        )
    return payload


def load_agent_lexicon_json(
    *,
    package: str,
    file_name: str,
    lexicons_subdir: Sequence[str] = ("lexicons",),
) -> dict[str, object]:
    """
    Load a packaged lexicon object for a v2 agent module.

    This mirrors `load_agent_prompt_markdown(...)` but for structured lexical
    defaults such as routing terms, fallback detection vocabularies, or
    canonical gap labels.
    """

    return load_packaged_json_object(
        package=package,
        path_parts=(*lexicons_subdir, file_name),
    )
