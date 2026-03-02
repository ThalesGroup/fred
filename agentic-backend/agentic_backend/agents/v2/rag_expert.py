# Copyright Thales 2025
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
First RAG-oriented agent definition for the v2 contract.

Why this file exists:
- It gives Fred a practical answer to "how do we express a useful RAG agent in
  the new model right now?" without immediately rebuilding the old bespoke RAG
  graph runtime.
- It deliberately reuses the shared ReAct runtime so the first migration step
  stays small: one execution engine, two definitions, clear comparison.
- It keeps tool access declarative, which is the part that aligns best with a
  future transport-agnostic SDK pattern.
"""

from __future__ import annotations

from pydantic import Field

from agentic_backend.core.agents.agent_spec import FieldSpec, UIHints
from agentic_backend.core.agents.v2 import (
    GuardrailDefinition,
    ReActAgentDefinition,
    ReActPolicy,
    ToolRefRequirement,
)
from agentic_backend.core.agents.v2.prompt_resources import (
    load_packaged_markdown,
)


DEFAULT_SYSTEM_PROMPT = load_packaged_markdown(
    package="agentic_backend",
    path_parts=("agents", "v2", "prompts", "rag_expert_system_prompt.md"),
)


class RagExpertV2Definition(ReActAgentDefinition):
    """
    Document-grounded assistant expressed as a ReAct definition.

    This is the standard v2 pattern for a business-facing RAG assistant:
    declare the prompt, the retrieval tool, and the business guardrails, then
    let the shared ReAct runtime handle the conversation and tool loop.

    In other words, this is already a proper v2 RAG agent. A more specialized
    runtime should only be introduced later if a concrete business need appears
    that the shared ReAct pattern cannot satisfy cleanly.

    Developer guide:
    - Choose `ReActAgentDefinition` when your agent is basically "prompt + tools
      + answer style". That is the case here: the business behavior is to search
      documents, then answer clearly from the results.
    - Edit `system_prompt_template` when you want to change the assistant's
      tone, grounding rules, or answer style.
    - Edit `tool_requirements` when you want to give the agent access to more
      business capabilities. Here we declare only one tool: `knowledge.search`.
    - Edit `fields` when you want the UI to expose business options such as
      file attachments, library selection, or RAG scope controls.
    - Edit `policy()` when you want to add or remove high-level business rules
      such as "be explicit when evidence is weak".

    In short, this file is where you describe what the RAG assistant should do
    for the user. You do not implement the search engine, the chat loop, or the
    streaming mechanism here.
    """

    agent_id: str = "rag.expert.v2"
    role: str = "Document-grounded RAG expert"
    description: str = (
        "A retrieval-augmented assistant that answers from selected documents "
        "and clearly distinguishes grounded evidence from uncertainty."
    )
    tags: tuple[str, ...] = ("rag", "documents", "react")
    # Main business instruction for the agent.
    # A developer edits this when they want to change how the assistant should
    # answer, cite, or talk to the user.
    system_prompt_template: str = Field(
        default=DEFAULT_SYSTEM_PROMPT,
        min_length=1,
    )
    # UI-exposed configuration for this agent.
    # A developer adds fields here when users should be able to tune behavior or
    # control the retrieval scope from the chat interface.
    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="system_prompt_template",
            type="prompt",
            title="RAG system prompt",
            description=(
                "High-level behavior for document-grounded answering. The shared "
                "runtime will render runtime-safe tokens such as {today} and "
                "{response_language}."
            ),
            required=True,
            default=DEFAULT_SYSTEM_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="chat_options.attach_files",
            type="boolean",
            title="Allow file attachments",
            description="Expose attachment controls so the user can scope the retrieval corpus.",
            required=False,
            default=True,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.libraries_selection",
            type="boolean",
            title="Document libraries picker",
            description="Expose document-library selection for retrieval scope control.",
            required=False,
            default=True,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.search_rag_scoping",
            type="boolean",
            title="RAG scope selector",
            description="Expose the retrieval-vs-general-knowledge scope selector.",
            required=False,
            default=True,
            ui=UIHints(group="Chat options"),
        ),
    )
    # Declared business capabilities available to the agent.
    # A developer adds tool refs here when the assistant should be allowed to
    # call more platform services.
    tool_requirements: tuple[ToolRefRequirement, ...] = (
        ToolRefRequirement(
            tool_ref="knowledge.search",
            description=(
                "Search the selected document libraries and session attachments "
                "and return relevant grounded snippets."
            ),
        ),
    )

    def policy(self) -> ReActPolicy:
        """
        Plain-English behavior contract for the shared ReAct runtime.

        Developer view:
        - `system_prompt_template` is the main instruction set for the agent.
        - `guardrails` are the key business rules that must stay obvious and
          readable without digging through the whole prompt text.

        In short, `policy()` is where you summarize how the agent should behave,
        while the runtime takes care of the chat loop and tool calling.
        """

        return ReActPolicy(
            system_prompt_template=self.system_prompt_template,
            guardrails=(
                GuardrailDefinition(
                    guardrail_id="grounding",
                    title="Ground answers in retrieved evidence",
                    description=(
                        "Do not present unsupported claims as if they came from the corpus."
                    ),
                ),
                GuardrailDefinition(
                    guardrail_id="uncertainty",
                    title="State uncertainty explicitly",
                    description=(
                        "When retrieval is missing or inconclusive, say so clearly instead of over-claiming."
                    ),
                ),
            ),
        )
