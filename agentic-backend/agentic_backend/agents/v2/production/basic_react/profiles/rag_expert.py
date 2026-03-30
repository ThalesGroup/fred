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

"""RAG expert starting profile."""

from agentic_backend.common.structures import AgentChatOptions
from agentic_backend.core.agents.v2 import (
    GuardrailDefinition,
    ToolRefRequirement,
)
from agentic_backend.core.agents.v2.support.builtins import (
    TOOL_REF_KNOWLEDGE_SEARCH,
)

from ..profile_model import ReActProfile
from ..profile_prompt_loader import load_basic_react_prompt

RAG_EXPERT_PROFILE = ReActProfile(
    profile_id="rag_expert",
    title="RAG Expert",
    description="Document-grounded assistant for retrieval-augmented Q&A.",
    role="Document-grounded RAG expert",
    agent_description=(
        "A retrieval-augmented assistant that answers from selected documents "
        "and clearly distinguishes grounded evidence from uncertainty."
    ),
    tags=("rag", "documents", "react"),
    system_prompt_template=load_basic_react_prompt(
        "basic_react_rag_expert_system_prompt.md"
    ),
    declared_tool_refs=(
        ToolRefRequirement(
            tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
            description=(
                "Search the selected document libraries and session attachments "
                "and return relevant grounded snippets."
            ),
        ),
    ),
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
                "When retrieval is missing or inconclusive, say so clearly "
                "instead of over-claiming."
            ),
        ),
    ),
    chat_options=AgentChatOptions(
        attach_files=True,
        libraries_selection=True,
        search_rag_scoping=True,
    ),
)
