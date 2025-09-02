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


import logging
from datetime import datetime
from typing import List

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, MessagesState, StateGraph

from fred_core import VectorSearchHit
from app.common.vector_search_client import VectorSearchClient
from app.common.rags_utils import (
    attach_sources_to_llm_response,
    ensure_ranks,
    format_sources_for_prompt,
    sort_hits,
)
from app.common.structures import AgentSettings
from app.core.agents.flow import AgentFlow
from app.core.agents.runtime_context import get_document_libraries_ids
from app.core.model.model_factory import get_model

logger = logging.getLogger(__name__)


def rag_preamble(now: str | None = None) -> str:
    now = now or datetime.now().strftime("%Y-%m-%d")
    return (
        "You are an assistant that answers questions strictly based on the retrieved document chunks. "
        "Always cite your claims using bracketed numeric markers like [1], [2], etc., matching the provided sources list. "
        "Be concise, factual, and avoid speculation. If evidence is weak or missing, say so.\n"
        f"Current date: {now}.\n"
    )


def build_rag_prompt(preamble: str, question: str, sources_block: str) -> str:
    return (
        f"{preamble}\n"
        "Use ONLY the sources below. When you state a fact, append a citation like [1] or [1][2]. "
        "If the sources disagree, say so briefly.\n\n"
        f"Question:\n{question}\n\n"
        f"Sources:\n{sources_block}\n"
    )


class RagExpert(AgentFlow):
    name: str = "RagExpert"
    nickname: str = "Remus"
    role: str = "Document Retrieval Expert"
    description: str = "Provides quick answers based on document content, using direct retrieval and generation."
    icon: str = "rags_agent"
    categories: List[str] = ["Documentation"]
    tag: str = "rags"

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings=agent_settings)

    async def async_init(self):
        self.model = get_model(self.agent_settings.model)
        self.search_client = VectorSearchClient()
        # Use shared preamble util
        self.base_prompt = rag_preamble(self.current_date)
        self._graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)
        builder.add_node("reasoner", self._run_reasoning_step)
        builder.add_edge(START, "reasoner")
        builder.add_edge("reasoner", END)
        return builder

    async def _run_reasoning_step(self, state: MessagesState):
        if self.model is None:
            raise RuntimeError(
                "Model is not initialized. Did you forget to call async_init()?"
            )

        msg = state["messages"][-1]
        if not isinstance(msg.content, str):
            raise TypeError(
                f"Expected string content, got: {type(msg.content).__name__}"
            )
        question = msg.content

        try:
            # Build search args
            top_k = 3
            tags = get_document_libraries_ids(self.get_runtime_context())

            # 1) Vector search via client
            hits: List[VectorSearchHit] = self.search_client.search(
                query=question, top_k=top_k, tags=tags
            )
            if not hits:
                warn = f"I couldn't find any relevant documents for “{question}”. Try rephrasing?"
                return {
                    "messages": [await self.model.ainvoke([HumanMessage(content=warn)])]
                }

            # 2) Deterministic ordering + fill ranks
            hits = sort_hits(hits)
            ensure_ranks(hits)

            # 3) Prompt build with shared utils
            sources_block = format_sources_for_prompt(hits, snippet_chars=500)
            prompt = build_rag_prompt(self.base_prompt, question, sources_block)

            # 4) Ask the model
            answer = await self.model.ainvoke([HumanMessage(content=prompt)])

            # 5) Attach rich sources metadata for the UI
            attach_sources_to_llm_response(answer, hits)

            return {"messages": [answer]}

        except Exception:
            logger.exception("Error in agent reasoning.")
            fallback = await self.model.ainvoke(
                [HumanMessage(content="An error occurred. Please try again later.")]
            )
            return {"messages": [fallback]}
