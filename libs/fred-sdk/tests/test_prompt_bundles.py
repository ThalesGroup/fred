from fred_sdk import apply_global_base_prompts

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
