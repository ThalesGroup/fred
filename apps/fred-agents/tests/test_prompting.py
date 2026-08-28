from fred_agents.general_assistant import GENERAL_ASSISTANT_AGENT
from fred_agents.rag_expert import RAG_EXPERT_AGENT
from fred_agents.react_rag_mcp import REACT_RAG_MCP_AGENT
from fred_agents.sentinel import SENTINEL_AGENT
from fred_agents.sql_expert import SQL_EXPERT_AGENT

_EXPECTED_FRAGMENT = "When you include Mermaid diagrams, follow these rules strictly so the diagram always parses:"
_EXPECTED_FALLBACK_RULE = "If you are unsure the Mermaid will parse, do not return Mermaid, return a simpler Markdown list or table instead."


def test_base_agents_do_not_bake_global_base_prompt_contract() -> None:
    """
    Verify no shipped fred-agents template bakes the global Mermaid rules.

    Why this test exists:
    - the Mermaid output contract moved from authoring-time baking to runtime
      injection (fred-runtime `build_global_base_prompt_suffix`)
    - the stored, operator-editable `system_prompt_template` must stay free of the
      contract so it does not clutter the agent editor and cannot be deleted by an
      operator; baking it back in is the regression this test guards against

    How to use it:
    - run via the default fred-agents test suite

    Example:
    - `pytest tests/test_prompting.py -q`
    """

    prompts = (
        GENERAL_ASSISTANT_AGENT.system_prompt_template,
        RAG_EXPERT_AGENT.system_prompt_template,
        REACT_RAG_MCP_AGENT.system_prompt_template,
        SENTINEL_AGENT.system_prompt_template,
        SQL_EXPERT_AGENT.system_prompt_template,
    )

    for prompt in prompts:
        assert _EXPECTED_FRAGMENT not in prompt
        assert _EXPECTED_FALLBACK_RULE not in prompt


def test_general_assistant_prompt_field_default_excludes_global_base_prompt() -> None:
    """
    Verify the general ReAct assistant's prompt field default is the bare prompt.

    Why this test exists:
    - the agent creation form pre-fills prompt fields from `FieldSpec.default`
    - that default must mirror `system_prompt_template` and must NOT carry the
      global Mermaid contract, which is now injected at runtime instead

    How to use it:
    - run via the default fred-agents test suite

    Example:
    - `pytest tests/test_prompting.py -q`
    """

    prompt_field = next(
        field
        for field in GENERAL_ASSISTANT_AGENT.fields
        if field.key == "prompts.system"
    )

    assert prompt_field.default == GENERAL_ASSISTANT_AGENT.system_prompt_template
    assert _EXPECTED_FRAGMENT not in str(prompt_field.default)
    assert _EXPECTED_FALLBACK_RULE not in str(prompt_field.default)
