# app/agents/rags/rico_expert.py
import logging
from datetime import datetime
from typing import List

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, MessagesState, StateGraph

from fred_core import VectorSearchHit
from app.common.rags_client import VectorSearchClient
from app.common.rags_prompt import build_rag_prompt, rag_preamble
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


class RicoExpert(AgentFlow):
    name: str = "RicoExpert"
    role: str = "Rags Expert"
    nickname: str = "Rico"
    description: str
    icon: str = "rags_agent"
    categories: List[str] = []
    tag: str = "Innovation"

    def __init__(self, agent_settings: AgentSettings):
        self.agent_settings = agent_settings
        self.name = agent_settings.name
        self.nickname = agent_settings.nickname or agent_settings.name
        self.role = agent_settings.role
        self.description = agent_settings.description
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.categories = agent_settings.categories or ["Documentation"]
        self.knowledge_flow_url = agent_settings.settings.get(
            "knowledge_flow_url", "http://localhost:8111/knowledge-flow/v1"
        )
        self.model = None
        self.base_prompt = ""
        self._graph = None
        self.tag = agent_settings.tag or "rags"

    async def async_init(self):
        self.model = get_model(self.agent_settings.model)
        self.search_client = VectorSearchClient(self.knowledge_flow_url, timeout_s=10)
        # Use shared preamble util
        self.base_prompt = rag_preamble(self.current_date)
        self._graph = self._build_graph()

        super().__init__(
            name=self.name,
            role=self.role,
            nickname=self.nickname,
            description=self.description,
            icon=self.icon,
            graph=self._graph,
            base_prompt=self.base_prompt,
            categories=self.categories,
            tag=self.tag,
        )

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
            logger.exception("Error in RicoExpert reasoning.")
            fallback = await self.model.ainvoke(
                [HumanMessage(content="An error occurred. Please try again later.")]
            )
            return {"messages": [fallback]}
