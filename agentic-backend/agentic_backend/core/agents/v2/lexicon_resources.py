from __future__ import annotations

import json
from collections.abc import Sequence
from importlib.resources.abc import Traversable

from .packaged_resources import load_packaged_resource


def _decode_json_object(resource_path: Traversable) -> dict[str, object]:
    try:
        payload = json.loads(resource_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid packaged JSON resource: {resource_path}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(
            f"Packaged JSON resource must contain an object at top level: {resource_path}"
        )
    return payload


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

    return load_packaged_resource(
        package=package,
        path_parts=path_parts,
        decoder=_decode_json_object,
        missing_resource_kind="JSON",
    )


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
