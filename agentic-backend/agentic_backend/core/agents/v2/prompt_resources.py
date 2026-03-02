from __future__ import annotations

from collections.abc import Sequence
from importlib.resources import files


def load_packaged_markdown(*, package: str, path_parts: Sequence[str]) -> str:
    """
    Load a packaged Markdown resource from an explicit package-relative path.

    Why this helper exists:
    - some prompt resources live under packages that should not be imported for
      their side effects during module initialization
    - v2 code needs one strict way to load packaged Markdown without reaching
      for ad hoc filesystem logic
    """

    if not path_parts:
        raise ValueError("path_parts must contain at least one path segment.")

    resource_path = files(package)
    for part in path_parts:
        resource_path = resource_path.joinpath(part)

    try:
        return resource_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Missing packaged Markdown resource: {resource_path}"
        ) from exc


def load_agent_prompt_markdown(
    *,
    package: str,
    file_name: str,
    prompts_subdir: Sequence[str] = ("prompts",),
) -> str:
    """
    Load a packaged Markdown prompt for a v2 agent module.

    Why this helper exists:
    - prompt text stays editable in dedicated `.md` files
    - agent definition modules stay focused on business intent
    - prompt loading stays strict and explicit for all v2 agents

    The `package` parameter should be the Python package that owns the
    `prompts/` directory, for example `agentic_backend.agents.v2`.
    """
    return load_packaged_markdown(
        package=package,
        path_parts=(*prompts_subdir, file_name),
    )
