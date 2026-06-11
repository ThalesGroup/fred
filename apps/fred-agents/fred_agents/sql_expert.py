# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
"""
Standalone SQL Expert ReAct agent definition.

Why this module exists:
- it ports the SQL Agent business profile into a direct `fred-sdk` definition
  that the standalone pod can serve without depending on agentic-backend
- it provides a focused SQL/tabular assistant using Knowledge Flow tabular MCP

How to use it:
- import `SQL_EXPERT_AGENT` and add it to a pod registry
- keep the prompt in `prompts/basic_react_sql_expert_system_prompt.md`
"""

from fred_sdk import (
    MCP_SERVER_KNOWLEDGE_FLOW_TABULAR,
    FieldSpec,
    GuardrailDefinition,
    MCPServerRef,
    UIHints,
    apply_global_base_prompts,
    load_agent_prompt_markdown,
)
from fred_sdk.contracts.models import ReActAgentDefinition, ReActPolicy


class SqlExpertReActDefinition(ReActAgentDefinition):
    """
    Tabular / SQL-focused ReAct agent served by the standalone agents pod.
    """

    agent_id: str = "fred.github.sql_expert"
    role: str = "Tabular SQL expert"
    description: str = (
        "A SQL-focused assistant that explores available tabular datasets, "
        "writes read-only SQL queries, executes them through Knowledge Flow "
        "tabular tools, and answers from the results."
    )
    tags: tuple[str, ...] = ("sql", "tabular", "react")
    system_prompt_template: str = apply_global_base_prompts(
        load_agent_prompt_markdown(
            package="fred_agents.sql_expert",
            file_name="basic_react_sql_expert_system_prompt.md",
        )
    )

    default_mcp_servers: tuple[MCPServerRef, ...] = (
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_TABULAR),
    )

    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System prompt",
            description=(
                "Override the default SQL expert instructions. "
                "Leave blank to use the built-in SQL reasoning prompt."
            ),
            required=False,
            ui=UIHints(group="Prompts", multiline=True, markdown=True, max_lines=12),
        ),
    )

    def policy(self) -> ReActPolicy:
        return ReActPolicy(
            system_prompt_template=self.system_prompt_template,
            guardrails=(
                GuardrailDefinition(
                    guardrail_id="read_only_sql",
                    title="Use read-only SQL only",
                    description=(
                        "Only generate safe read-only SQL queries. "
                        "Never propose INSERT, UPDATE, DELETE, DROP, ALTER, or TRUNCATE."
                    ),
                ),
                GuardrailDefinition(
                    guardrail_id="no_invented_schema",
                    title="Do not invent schema elements",
                    description=(
                        "Do not invent tables, databases, or columns that are not present "
                        "in the surfaced tabular context."
                    ),
                ),
                GuardrailDefinition(
                    guardrail_id="clarify_ambiguity",
                    title="Clarify ambiguous scope",
                    description=(
                        "If several databases or tables could match the request and the "
                        "correct scope is unclear, ask the user for clarification."
                    ),
                ),
            ),
        )


SQL_EXPERT_AGENT = SqlExpertReActDefinition()
