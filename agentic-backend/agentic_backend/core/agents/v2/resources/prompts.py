from __future__ import annotations

from collections.abc import Sequence

from .packaged import load_packaged_resource


def load_packaged_markdown(*, package: str, path_parts: Sequence[str]) -> str:
    """
    Load a packaged Markdown resource from an explicit package-relative path.

    Why this helper exists:
    - some prompt resources live under packages that should not be imported for
      their side effects during module initialization
    - v2 code needs one strict way to load packaged Markdown without reaching
      for ad hoc filesystem logic

    How to use it:
    - pass the owning package and the relative path segments to the Markdown file

    Example:
    - `text = load_packaged_markdown(package="agentic_backend", path_parts=("agents", "v2", "production", "basic_react", "prompts", "system.md"))`
    """

    return load_packaged_resource(
        package=package,
        path_parts=path_parts,
        decoder=lambda resource_path: resource_path.read_text(encoding="utf-8"),
        missing_resource_kind="Markdown",
    )


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

    How to use it:
    - pass the package owning the `prompts/` directory and the file name to load

    Example:
    - `prompt = load_agent_prompt_markdown(package="my_package.agents.search_agent", file_name="system_prompt.md")`
    """
    return load_packaged_markdown(
        package=package,
        path_parts=(*prompts_subdir, file_name),
    )
