"""
Small resource-loading helpers used by v2 agent authors.

Why this package exists:
- prompt files and other packaged text resources are part of the author-facing
  SDK surface
- grouping them here keeps author utilities separate from runtime internals

How to use it:
- import `load_packaged_markdown(...)` when an agent module wants to load a
  packaged `.md` file by explicit path
- import `load_agent_prompt_markdown(...)` when an authored agent wants the
  conventional `prompts/<file>` lookup

Example:
- `system_prompt = load_packaged_markdown(package=\"my_pkg\", path_parts=(\"prompts\", \"system.md\"))`
"""

from .prompts import load_agent_prompt_markdown, load_packaged_markdown

__all__ = [
    "load_agent_prompt_markdown",
    "load_packaged_markdown",
]
