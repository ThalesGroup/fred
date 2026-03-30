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
Input and state for the Archie v2 RAG agent.

Archie retrieves relevant document chunks then synthesises a grounded answer.
"""

from __future__ import annotations

from fred_core.store import VectorSearchHit
from pydantic import BaseModel, Field


class ArchieInput(BaseModel):
    """User question that starts one Archie run."""

    message: str = Field(..., min_length=1)


class ArchieState(BaseModel):
    """
    Business state carried through the Archie workflow.

    Prompt fields and retrieval config are injected at workflow start from the
    definition's tunable fields via ArchieV2Definition.build_initial_state.
    Editing them in the UI settings takes effect on the next run.
    """

    # ── Input ──────────────────────────────────────────────────────────────
    question: str

    # ── Prompts (injected from definition fields at workflow start) ─────────
    system_prompt: str = ""
    with_sources_prompt: str = ""
    no_sources_prompt: str = ""

    # ── Retrieval config (injected from definition fields at workflow start) ─
    top_k: int = 8
    min_score: float = 0.6

    # ── Step results ───────────────────────────────────────────────────────
    hits: list[VectorSearchHit] = Field(default_factory=list)
    filtered_hits: list[VectorSearchHit] = Field(default_factory=list)

    # ── Final output ───────────────────────────────────────────────────────
    final_text: str | None = None
