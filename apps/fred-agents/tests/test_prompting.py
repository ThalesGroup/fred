from fred_agents.general_assistant import GENERAL_ASSISTANT_AGENT
from fred_agents.rag_expert import RAG_EXPERT_AGENT
from fred_agents.react_rag_mcp import REACT_RAG_MCP_AGENT
from fred_agents.sentinel import SENTINEL_AGENT
from fred_agents.sql_expert import SQL_EXPERT_AGENT

_EXPECTED_FRAGMENT = "When you include Mermaid diagrams, follow these rules strictly so the diagram always parses:"
_EXPECTED_FALLBACK_RULE = "If you are unsure the Mermaid will parse, do not return Mermaid, return a simpler Markdown list or table instead."


def test_all_base_agents_include_global_base_prompt_contract() -> None:
    """
    Verify every shipped fred-agents base prompt includes the global Mermaid rules.

    Why this test exists:
    - the Mermaid output contract should apply uniformly to every default agent
    - one regression in prompt composition would otherwise silently reintroduce
      broken diagrams for some templates only

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
        assert _EXPECTED_FRAGMENT in prompt
        assert _EXPECTED_FALLBACK_RULE in prompt
