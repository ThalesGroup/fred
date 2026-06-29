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
Standalone RAG Expert ReAct agent definition.

Why this module exists:
- it ports the RAG Expert business profile into a direct `fred-sdk` definition
  that the standalone pod can serve without depending on agentic-backend
- it is a reference example of a Fred agent that relies on a first-class
  platform tool ref (`knowledge.search`) rather than an MCP server

How to use it:
- import `RAG_EXPERT_AGENT` and add it to a pod registry
- keep the prompt in `prompts/basic_react_rag_expert_system_prompt.md`

Example:
- `from fred_agents.rag_expert import RAG_EXPERT_AGENT`
"""

from fred_sdk import (
    TOOL_REF_KNOWLEDGE_SEARCH,
    FieldSpec,
    GuardrailDefinition,
    ToolRefRequirement,
    UIHints,
    load_agent_prompt_markdown,
)
from fred_sdk.contracts.models import ReActAgentDefinition, ReActPolicy

# The shared global base prompt (Mermaid output contract) is injected at
# execution time by the runtime, not baked into this editable template.
_RAG_EXPERT_SYSTEM_PROMPT: str = load_agent_prompt_markdown(
    package="fred_agents.rag_expert",
    file_name="basic_react_rag_expert_system_prompt.md",
)


class RagExpertReActDefinition(ReActAgentDefinition):
    """
    Document-grounded ReAct agent served by the standalone agents pod.

    Why this class exists:
    - it provides a production-quality RAG assistant that grounds every answer
      in evidence retrieved from the user-selected document corpus
    - it demonstrates the `declared_tool_refs` pattern (first-class Fred platform
      tools) as opposed to the `default_mcp_servers` pattern (external MCP servers)

    Key design choices:
    - `declared_tool_refs` declares `knowledge.search` — the Fred built-in
      retrieval tool — so the runtime can bind it at execution time
    - guardrails are kept inside `policy()`, not on the class, because they are
      operating constraints that the runtime enforces, not authoring metadata
    - no MCP servers are declared: RAG grounding is a Fred first-class concern

    How to use it:
    - instantiate it once and register it in the pod registry
    - extend `declared_tool_refs` if additional retrieval tools are introduced

    Example:
    - `definition = RagExpertReActDefinition()`
    """

    agent_id: str = "fred.github.rag_expert"
    role: str = "Rico"
    description: str = (
        "A retrieval-augmented assistant that answers from selected document "
        "libraries and clearly distinguishes grounded evidence from uncertainty."
    )
    tags: tuple[str, ...] = ("rag", "documents", "react")
    system_prompt_template: str = _RAG_EXPERT_SYSTEM_PROMPT
    declared_tool_refs: tuple[ToolRefRequirement, ...] = (
        ToolRefRequirement(
            tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
            description=(
                "Search the selected document libraries and session attachments "
                "and return relevant grounded snippets."
            ),
        ),
    )

    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System prompt",
            description=(
                "Override the default RAG expert grounding instructions. "
                "Leave blank to use the built-in document-grounded reasoning prompt."
            ),
            required=False,
            ui=UIHints(
                group="Prompts",
                multiline=True,
                markdown=True,
                max_lines=12,
                placeholder=_RAG_EXPERT_SYSTEM_PROMPT,
            ),
        ),
    )

    def policy(self) -> ReActPolicy:
        """
        Return the RAG Expert conversational policy for the ReAct runtime.

        Why this function exists:
        - `ReActRuntime` drives standalone pod agents through a pure `ReActPolicy`
        - guardrails are declared here because they are runtime operating
          constraints, not agent authoring metadata

        How to use it:
        - call indirectly through `ReActRuntime`; authors set class fields and
          keep this method focused on policy assembly

        Example:
        - `policy = RagExpertReActDefinition().policy()`
        """

        return ReActPolicy(
            system_prompt_template=self.system_prompt_template,
            guardrails=(
                GuardrailDefinition(
                    guardrail_id="grounding",
                    title="Ground claims in corpus evidence",
                    description=(
                        "Do not present unsupported claims as if they came from "
                        "the retrieved corpus."
                    ),
                ),
                GuardrailDefinition(
                    guardrail_id="uncertainty",
                    title="State uncertainty explicitly",
                    description=(
                        "When retrieval is missing or inconclusive, say so clearly "
                        "instead of over-claiming."
                    ),
                ),
            ),
        )


RAG_EXPERT_AGENT = RagExpertReActDefinition()
