# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Report Generator — deep agent that produces structured, grounded reports.

Why this module exists:
- provides a DeepAgentDefinition-backed template in the Create Agent menu
  under the "deep" category pill
- uses DeepAgentRuntime (deepagents planner) rather than plain ReAct so the
  agent can decompose multi-step research before writing

How to use it:
- import REPORT_GENERATOR_AGENT and add it to the pod registry
- user picks it from "Create Agent", asks "generate a report on <topic>"
"""

from fred_sdk import (
    MCP_SERVER_KNOWLEDGE_FLOW_CORPUS,
    MCP_SERVER_KNOWLEDGE_FLOW_TEXT,
    FieldSpec,
    MCPServerRef,
    UIHints,
    apply_global_base_prompts,
)
from fred_sdk.contracts.models import DeepAgentDefinition, ReActPolicy

_SYSTEM_PROMPT = apply_global_base_prompts(
    """\
You are a professional report-writing assistant.

When the user asks you to generate a report, you must:
1. Clarify the topic and scope if not clear.
2. Search available knowledge sources to gather relevant information.
3. Organise findings into clearly labelled sections: Executive Summary, \
Background, Key Findings, Conclusion.
4. Cite every claim with the source document or tool result that produced it.
5. Return the full report as structured markdown.

If no search tools are available, state this clearly and produce a best-effort \
report from your training knowledge, marking all unsourced claims as [unverified].
"""
)


class ReportGeneratorDefinition(DeepAgentDefinition):
    """Deep agent that researches a topic and writes a structured report."""

    agent_id: str = "fred.github.report_generator"
    role: str = "Report Generator"
    description: str = (
        "Deep agent that researches a topic across available knowledge sources "
        "and produces a structured, cited report. Ask it: 'generate a report on <topic>'."
    )
    description_by_lang: dict[str, str] | None = {
        "fr": (
            "Agent avancé qui recherche un sujet dans les sources de connaissance "
            "disponibles et produit un rapport structuré et sourcé. "
            "Demandez-lui : 'génère un rapport sur <sujet>'."
        )
    }
    tags: tuple[str, ...] = ("deep", "report", "research")
    system_prompt_template: str = _SYSTEM_PROMPT

    default_mcp_servers: tuple[MCPServerRef, ...] = (
        MCPServerRef(id="mcp-web-search-google"),
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_TEXT),
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_CORPUS),
    )

    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System prompt",
            description="Instructions that define the report style and focus.",
            description_by_lang={
                "fr": "Instructions définissant le style et le périmètre du rapport."
            },
            required=False,
            default=_SYSTEM_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True, max_lines=12),
        ),
    )

    def policy(self) -> ReActPolicy:
        return ReActPolicy(system_prompt_template=self.system_prompt_template)


REPORT_GENERATOR_AGENT = ReportGeneratorDefinition()
