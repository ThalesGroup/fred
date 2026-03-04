"""Shared helpers for Basic ReAct profile declarations."""

from agentic_backend.core.agents.v2.prompt_resources import load_packaged_markdown


def load_basic_react_prompt(file_name: str) -> str:
    """Load a packaged prompt from `agents/v2/production/basic_react/prompts/`."""

    return load_packaged_markdown(
        package="agentic_backend",
        path_parts=(
            "agents",
            "v2",
            "production",
            "basic_react",
            "prompts",
            file_name,
        ),
    )
