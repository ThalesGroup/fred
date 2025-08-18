# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# ...

import logging
from datetime import datetime
from typing import Any, Dict, List

import requests
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, MessagesState, StateGraph

from fred_core import VectorSearchHit
from app.common.structures import AgentSettings
from app.core.agents.flow import AgentFlow
from app.core.agents.runtime_context import get_document_libraries_ids
from app.core.model.model_factory import get_model

logger = logging.getLogger(__name__)


class RicoExpert(AgentFlow):
    """
    RAGs Expert:
    - Queries Knowledge Flow vector search
    - Builds a citation-friendly prompt with ranked sources
    - Returns LLM answer + rich sources metadata for the UI
    """

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
        self.base_prompt = self._generate_prompt()
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

    def _generate_prompt(self) -> str:
        # Keep this short; we’ll append the dynamic sources per question.
        return (
            "You are an assistant that answers questions strictly based on the retrieved document chunks. "
            "Always cite your claims using bracketed numeric markers like [1], [2], etc., matching the provided sources list. "
            "Be concise, factual, and avoid speculation. If evidence is weak or missing, say so.\n"
            f"Current date: {self.current_date}.\n"
        )

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)
        builder.add_node("reasoner", self._run_reasoning_step)
        builder.add_edge(START, "reasoner")
        builder.add_edge("reasoner", END)
        return builder

    @staticmethod
    def _format_sources_for_prompt(hits: List[VectorSearchHit]) -> str:
        """
        Turn hits into a numbered list of short source entries
        that the model can cite as [1], [2], ...
        """
        lines: List[str] = []
        for h in hits:
            # Build a compact, readable label per hit
            label_bits = []
            if h.title:
                label_bits.append(h.title)
            if h.section:
                label_bits.append(f"§ {h.section}")
            if h.page is not None:
                label_bits.append(f"p.{h.page}")
            if h.file_name:
                label_bits.append(f"({h.file_name})")
            if h.tag_names:
                label_bits.append(f"tags: {', '.join(h.tag_names)}")

            label = " — ".join(label_bits) if label_bits else h.uid
            # Include a short content snippet to steer the model
            snippet = (h.content or "").strip()
            if len(snippet) > 500:
                snippet = snippet[:500] + "…"

            lines.append(f"[{h.rank}] {label}\n{snippet}")
        return "\n\n".join(lines)

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
            # 1) Build search request
            request_data: Dict[str, Any] = {"query": question, "top_k": 3}

            library_ids = get_document_libraries_ids(self.get_runtime_context())
            if library_ids:
                request_data["tags"] = library_ids
                logger.info("RicoExpert filtering by libraries: %s", library_ids)

            # 2) Call Knowledge Flow vector search
            resp = requests.post(
                f"{self.knowledge_flow_url}/vector/search",
                json=request_data,
                timeout=10,
            )
            resp.raise_for_status()
            raw = resp.json()  # expect a list of VectorSearchHit-like dicts

            if not raw:
                msg = f"I couldn't find any relevant documents for “{question}”. Try rephrasing?"
                return {
                    "messages": [await self.model.ainvoke([HumanMessage(content=msg)])]
                }

            # 3) Parse + sort by rank just in case
            hits: List[VectorSearchHit] = [VectorSearchHit(**d) for d in raw]
            hits.sort(key=lambda h: (h.rank or 1_000_000, -h.score))

            # 4) Build a clear, citation-friendly prompt
            sources_block = self._format_sources_for_prompt(hits)
            prompt = (
                f"{self.base_prompt}\n"
                "Use ONLY the sources below. When you state a fact, append a citation like [1] or [1][2]. "
                "If the sources disagree, say so briefly.\n\n"
                f"Question:\n{question}\n\n"
                f"Sources:\n{sources_block}\n"
            )

            # 5) Ask the model
            answer = await self.model.ainvoke([HumanMessage(content=prompt)])

            # 6) Attach rich sources metadata for the UI
            answer.response_metadata["sources"] = [h.model_dump() for h in hits]

            return {"messages": [answer]}

        except Exception:
            logger.exception("Error in RicoExpert reasoning.")
            fallback = await self.model.ainvoke(
                [HumanMessage(content="An error occurred. Please try again later.")]
            )
            return {"messages": [fallback]}
