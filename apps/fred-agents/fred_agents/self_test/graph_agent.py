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

"""The deterministic self-test RAG agent (`fred.github.self_test`).

A managed-executable graph agent with one job: retrieve from the per-turn
selected libraries through the real knowledge-search tool and return the
retrieved chunks verbatim (no LLM). The admin self-test page invokes it through
the real execution pipeline and asserts a marker phrase is present in the answer
(library A) or absent (library B). See ADMIN-SELF-TEST-HARNESS-RFC §A.4.
"""

from __future__ import annotations

from fred_core.store import VectorSearchHit
from fred_sdk import (
    TOOL_REF_KNOWLEDGE_SEARCH,
    FieldSpec,
    GraphAgent,
    GraphWorkflow,
    ToolRefRequirement,
    UIHints,
)
from fred_sdk.graph.runtime import GraphExecutionOutput
from pydantic import BaseModel

from .graph_state import SelfTestInput, SelfTestState
from .graph_steps import finalize_step, retrieve_step


class SelfTestGraphAgent(GraphAgent):
    """No-LLM RAG agent used by the admin self-test harness (VALID-02)."""

    agent_id: str = "fred.github.self_test"
    role: str = "Self-Test (RAG, deterministic)"
    description: str = (
        "Deterministic RAG self-test agent (no LLM). Retrieves from the selected "
        "libraries via the real knowledge-search tool and echoes the retrieved "
        "chunks verbatim, so the admin self-test page can assert a marker phrase "
        "was retrieved end-to-end through the real execution pipeline."
    )
    tags: tuple[str, ...] = ("test", "rag", "deterministic", "no-llm")
    # Internal harness agent: registered + executable, but hidden from the
    # "create agent" catalog. The self-test page enrolls it via the
    # include_non_public escape hatch. See AGENT-VISIBILITY-RFC.
    public: bool = False

    declared_tool_refs: tuple[ToolRefRequirement, ...] = (
        ToolRefRequirement(
            tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
            required=True,
            description="Real RAG retrieval, scoped to the per-turn selected libraries.",
        ),
    )

    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System prompt",
            description=(
                "Per-instance system prompt. The agent echoes it back so the "
                "self-test harness can assert the tuning-prompt path is delivered "
                "end-to-end (enrollment → tuning → runtime → agent)."
            ),
            default="",
            ui=UIHints(group="Prompts"),
        ),
        FieldSpec(
            key="settings.top_k",
            type="integer",
            title="Top-K results",
            description="Number of chunks to retrieve and echo.",
            default=5,
            min=1,
            max=50,
            ui=UIHints(group="Settings"),
        ),
        FieldSpec(
            key="chat_options.libraries_selection",
            type="boolean",
            title="Document library picker",
            description="Expose the library scoper in chat so a scope can be selected.",
            default=True,
            ui=UIHints(group="Chat options"),
        ),
    )

    input_schema = SelfTestInput
    state_schema = SelfTestState
    input_to_state = {"message": "latest_user_text"}
    output_state_field = "final_text"

    workflow = GraphWorkflow(
        entry="retrieve",
        nodes={"retrieve": retrieve_step, "finalize": finalize_step},
        edges={"retrieve": "finalize"},
    )

    def build_output(self, state: BaseModel) -> BaseModel:
        """Attach the retrieved chunks as sources on the final SSE event."""
        assert isinstance(state, SelfTestState)
        sources = tuple(
            VectorSearchHit.model_validate(raw) for raw in state.sources_data
        )
        return GraphExecutionOutput(content=state.final_text or "", sources=sources)


SELF_TEST_AGENT = SelfTestGraphAgent()
