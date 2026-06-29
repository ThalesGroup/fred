from fred_sdk import (
    load_agent_prompt_markdown,
    load_packaged_markdown,
)
from fred_sdk.resources.prompts import GLOBAL_BASE_PROMPT_MARKDOWN

_EXPECTED_FRAGMENT = "When you include Mermaid diagrams, follow these rules strictly so the diagram always parses:"
_EXPECTED_FALLBACK_RULE = "If you are unsure the Mermaid will parse, do not return Mermaid, return a simpler Markdown list or table instead."


def test_global_base_prompt_markdown_bundles_mermaid_contract() -> None:
    """
    Verify the SDK-owned global base prompt bundle carries the Mermaid contract.

    Why this test exists:
    - `GLOBAL_BASE_PROMPT_MARKDOWN` is the single source of truth that the runtime
      injects at execution time (see fred-runtime `build_global_base_prompt_suffix`)
    - the contract is no longer baked into agent templates, so this constant is the
      only place that still guarantees the renderer rules ship with the platform

    How to use it:
    - run via the default fred-sdk test suite

    Example:
    - `pytest tests/test_prompt_bundles.py -q`
    """

    assert _EXPECTED_FRAGMENT in GLOBAL_BASE_PROMPT_MARKDOWN
    assert _EXPECTED_FALLBACK_RULE in GLOBAL_BASE_PROMPT_MARKDOWN


def test_load_agent_prompt_markdown_does_not_append_global_base_prompt() -> None:
    """
    Verify the conventional agent prompt loader returns the raw file only.

    Why this test exists:
    - the global base prompt moved from authoring-time baking to runtime injection;
      `load_agent_prompt_markdown` must return exactly the packaged file with no
      shared renderer/output contract appended

    How to use it:
    - run via the default fred-sdk test suite

    Example:
    - `pytest tests/test_prompt_bundles.py -q`
    """

    base_prompt = load_packaged_markdown(
        package="fred_sdk",
        path_parts=("resources", "prompts", "mermaid_output_contract.md"),
    )
    prompt = load_agent_prompt_markdown(
        package="fred_sdk.resources",
        file_name="mermaid_output_contract.md",
    )

    # The loader returns the file verbatim — the contract appears exactly once,
    # not twice (no global base prompt is appended).
    assert prompt == base_prompt
    assert prompt.count(_EXPECTED_FRAGMENT) == 1


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
