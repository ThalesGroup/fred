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
DocStubExpert — tiny mock "document expert".

Why this exists:
- Lets us test the orchestrator without wiring retrieval/RAG.
- Always returns a small, deterministic answer + mock "sources".
- Keeps the contract identical to real experts: input messages → AIMessage.
"""

from __future__ import annotations

from typing import Sequence

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage

from agentic_backend.core.agents.agent_spec import AgentTuning
from agentic_backend.core.agents.simple_agent_flow import SimpleAgentFlow

TUNING = AgentTuning(
    role="Mini Doc Expert",
    description=(
        "A mock document-grounded expert that simulates answering questions "
        "using retrieved documents. Returns a hard-coded answer with fake sources."
    ),
    tags=["academy"],
)


class MiniRagExpert(SimpleAgentFlow):
    """
    Hover intent:
    - This expert simulates a grounded doc answer so LeaderFlow integration
      and UI rendering (sources, metadata) can be tested safely.
    """

    tuning = TUNING

    async def arun(self, *, messages: Sequence[AnyMessage]) -> AIMessage:
        # Why a trivial read of the last user message:
        # - Keeps a realistic shape for later swap with real RAG (same method signature).
        last_user = next(
            (m for m in reversed(messages) if isinstance(m, HumanMessage)), None
        )
        question = last_user.content if last_user else ""

        # Hard-coded, deterministic output with mock sources
        content = (
            "Answer (doc expert): This is a concise, grounded response.\n"
            f"Re: “{question}”\n\n"
            "Key point: we simulate a precise citation style.\n"
            "Sources: [DOC-001], [DOC-002]"
        )
        return AIMessage(
            content=content,
            additional_kwargs={
                "fred": {
                    "sources": [
                        {
                            "id": "DOC-001",
                            "title": "Spec Overview",
                            "url": "about:blank",
                        },
                        {
                            "id": "DOC-002",
                            "title": "Design Notes",
                            "url": "about:blank",
                        },
                    ],
                    "expert": "doc_stub",
                }
            },
        )
