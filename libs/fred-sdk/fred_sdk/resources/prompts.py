from __future__ import annotations

from collections.abc import Sequence

from .packaged import load_packaged_resource

# Add one `(package, path_parts)` tuple here for each shared prompt fragment
# that should be available to authored agent pods. Fragments are appended in
# declaration order.
GLOBAL_BASE_PROMPT_RESOURCES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("fred_sdk", ("resources", "prompts", "mermaid_output_contract.md")),
)


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
    - `text = load_packaged_markdown(package="fred_sdk", path_parts=("resources", "prompts", "system.md"))`
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
    include_global_base_prompts: bool = False,
) -> str:
    """
    Load a packaged Markdown prompt for a v2 agent module.

    Why this helper exists:
    - prompt text stays editable in dedicated `.md` files
    - agent definition modules stay focused on business intent
    - prompt loading stays strict and explicit for all v2 agents

    The `package` parameter should be the Python package that owns the
    `prompts/` directory, for example `fred_sdk.resources`.

    How to use it:
    - pass the package owning the `prompts/` directory and the file name to load
    - set `include_global_base_prompts=True` for default system prompts that
      should inherit Fred's shared renderer/output contracts

    Example:
    - `prompt = load_agent_prompt_markdown(package="my_package.agents.search_agent", file_name="system_prompt.md", include_global_base_prompts=True)`
    """
    prompt = load_packaged_markdown(
        package=package,
        path_parts=(*prompts_subdir, file_name),
    )
    if include_global_base_prompts:
        return apply_global_base_prompts(prompt)
    return prompt


def _join_prompt_sections(sections: Sequence[str]) -> str:
    return "\n\n".join(section for section in sections if section)


GLOBAL_BASE_PROMPT_MARKDOWN: str = _join_prompt_sections(
    tuple(
        load_packaged_markdown(package=package, path_parts=path_parts).strip()
        for package, path_parts in GLOBAL_BASE_PROMPT_RESOURCES
    )
)


def apply_global_base_prompts(prompt: str) -> str:
    """
    Append Fred's shared base prompt fragments to one agent prompt.

    Why this helper exists:
    - renderer-oriented output contracts should be reusable across agent pods
      instead of copied into each application package
    - prompt composition remains an authoring-time default, not a runtime
      injection layer

    How to use it:
    - pass the agent's local system prompt and assign the returned text to the
      template's default `system_prompt_template`

    Example:
    - `system_prompt_template = apply_global_base_prompts(local_prompt)`
    """

    return _join_prompt_sections((prompt.strip(), GLOBAL_BASE_PROMPT_MARKDOWN))
