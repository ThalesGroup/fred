"""Shared helpers for Basic ReAct profile declarations."""

from agentic_backend.core.agents.v2.resources import load_agent_prompt_markdown

_BASIC_REACT_PROFILE_PACKAGE = "agentic_backend.agents.v2.production.basic_react"


def load_basic_react_prompt(file_name: str) -> str:
    """
    Load one Basic ReAct prompt template by file name.

    Why this helper exists:
    - Basic ReAct profiles should stay focused on business intent, not prompt
      packaging details
    - prompt files remain editable as Markdown next to the Basic ReAct agent
      package without exposing that directory layout to every profile module

    How to use it:
    - pass the prompt file name stored in the Basic ReAct prompt package

    Example:
    - `prompt = load_basic_react_prompt("basic_react_sentinel_system_prompt.md")`
    """

    return load_agent_prompt_markdown(
        package=_BASIC_REACT_PROFILE_PACKAGE,
        file_name=file_name,
    )
