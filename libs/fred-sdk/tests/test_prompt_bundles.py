from fred_sdk import (
    apply_global_base_prompts,
    load_agent_prompt_markdown,
    load_packaged_markdown,
)

_EXPECTED_FRAGMENT = "When you include Mermaid diagrams, follow these rules strictly so the diagram always parses:"
_EXPECTED_FALLBACK_RULE = "If you are unsure the Mermaid will parse, do not return Mermaid, return a simpler Markdown list or table instead."


def test_apply_global_base_prompts_appends_mermaid_contract() -> None:
    """
    Verify the SDK-owned shared prompt bundle appends the Mermaid output contract.

    Why this test exists:
    - shared prompt fragments are loaded as packaged SDK resources and should
      remain available to every agent pod

    How to use it:
    - run via the default fred-sdk test suite

    Example:
    - `pytest tests/test_prompt_bundles.py -q`
    """

    prompt = apply_global_base_prompts("Local instructions.")

    assert prompt.startswith("Local instructions.")
    assert _EXPECTED_FRAGMENT in prompt
    assert _EXPECTED_FALLBACK_RULE in prompt


def test_load_agent_prompt_markdown_can_include_global_base_prompts() -> None:
    """
    Verify the conventional agent prompt loader can opt into shared base prompts.

    Why this test exists:
    - default agent modules should be able to declare shared prompt composition
      at the load site without nesting `apply_global_base_prompts(...)`

    How to use it:
    - pass `include_global_base_prompts=True` when loading a system prompt file

    Example:
    - `load_agent_prompt_markdown(package="fred_sdk.resources", file_name="sample.md", include_global_base_prompts=True)`
    """

    base_prompt = load_packaged_markdown(
        package="fred_sdk",
        path_parts=("resources", "prompts", "mermaid_output_contract.md"),
    )
    prompt = load_agent_prompt_markdown(
        package="fred_sdk.resources",
        file_name="mermaid_output_contract.md",
        include_global_base_prompts=True,
    )

    assert prompt.startswith(base_prompt)
    assert prompt.count(_EXPECTED_FRAGMENT) == 2
    assert prompt.count(_EXPECTED_FALLBACK_RULE) == 2


def test_mermaid_contract_does_not_embed_executable_placeholder_fences() -> None:
    """
    Verify the shared Mermaid prompt is safe to render as Markdown documentation.

    Why this test exists:
    - the contract itself is injected into agent prompts and may be shown back
      in debug or prompt-review surfaces
    - placeholder or invalid `mermaid` fences would make the frontend renderer
      attempt to execute broken diagrams

    How to use it:
    - keep syntax examples in prose or `text` fences unless they are complete
      valid diagrams

    Example:
    - `assert "```mermaid" not in mermaid_contract`
    """

    contract = load_packaged_markdown(
        package="fred_sdk",
        path_parts=("resources", "prompts", "mermaid_output_contract.md"),
    )

    assert "```mermaid" not in contract
    assert "placeholder Mermaid fences" in contract


def test_mermaid_contract_forbids_nested_fences_and_fragile_subgraphs() -> None:
    """
    Verify the shared Mermaid prompt blocks the fragile forms seen in rendering errors.

    Why this test exists:
    - Mermaid receives only diagram source; if the source still contains
      Markdown fences or a nested four-backtick example wrapper, the renderer
      reports that no diagram type was detected
    - diagrams that start directly with `subgraph` fail for the same reason:
      Mermaid cannot detect the diagram type
    - `subgraph ID["Title"]` looks like node-label syntax but is fragile for
      subgraph declarations

    How to use it:
    - keep Mermaid fence contents bare: first line `flowchart TD`, no backticks
      inside the block, and conservative subgraph declarations

    Example:
    - `flowchart TD` followed by `subgraph SERVICE_AI`
    """

    contract = load_packaged_markdown(
        package="fred_sdk",
        path_parts=("resources", "prompts", "mermaid_output_contract.md"),
    )

    assert "do not include the opening or closing backticks themselves" in contract
    assert "Never nest a Mermaid fence inside another Mermaid fence" in contract
    assert (
        "Never wrap a Mermaid fence inside a four-backtick Markdown fence" in contract
    )
    assert "use a `text` fence and label it as non-rendered" in contract
    assert (
        "The first non-empty line inside every Mermaid fence must be `flowchart TD` or `graph TD`"
        in contract
    )
    assert "Never start a Mermaid diagram directly with backticks" in contract
    assert (
        "The response contains no four-backtick fence around Mermaid content"
        in contract
    )
    assert "Do not write subgraph titles with node-label syntax" in contract
    assert 'subgraph SUBGRAPH_ID["Title"]' in contract
