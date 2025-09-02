# app/agents/dominic/dominic.py
# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# ...

import json
import logging
from typing import List

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import tools_condition

from app.common.mcp_runtime import MCPRuntime
from app.common.resilient_tool_node import make_resilient_tools_node
from app.common.structures import AgentSettings
from app.core.agents.flow import AgentFlow
from app.core.model.model_factory import get_model

from fred_core import VectorSearchHit
from pydantic import TypeAdapter, ValidationError

logger = logging.getLogger(__name__)


class DocumentExpert(AgentFlow):
    """
    Tool-first documents expert using MCP.
    - The model decides when to call the MCP tool `search_documents_using_vectorization`.
    - Results are strict VectorSearchHit and are attached to response metadata for the UI.
    """

    name: str = "DocumentExpert"
    nickname: str = "Dominic"
    role: str = "Document Expert using basic RAG"
    description: str = "Performs basic RAG (Retrieval Augmented Generation)"
    icon: str = "documents_agent"
    categories: list[str] = ["Documentation"]
    tag: str = "rags"

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings=agent_settings)
        self.mcp = MCPRuntime(
            agent_settings=agent_settings,
            # If you expose runtime filtering (tenant/library/time window),
            # pass a provider: lambda: self.get_runtime_context()
            context_provider=(lambda: self.get_runtime_context()),
        )
        self.base_prompt = self._generate_prompt()

        # Typed adapter for validating tool outputs into List[VectorSearchHit]
        self._hits_adapter: TypeAdapter[List[VectorSearchHit]] = TypeAdapter(
            List[VectorSearchHit]
        )

    async def async_init(self):
        self.model = get_model(self.agent_settings.model)
        await self.mcp.init()
        self.model = self.model.bind_tools(self.mcp.get_tools())
        self._graph = self._build_graph()

    def _generate_prompt(self) -> str:
        return (
            "You are a documents expert. Use the available MCP tools to retrieve factual content, "
            "then answer strictly based on those results.\n"
            "When you state a fact, add bracketed source markers like [1], [2]. If evidence is weak or missing, say so.\n"
            "Always try the vector search tool before answering.\n"
            f"Current date: {self.current_date}.\n"
        )

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)
        builder.add_node("reasoner", self.reasoner)

        async def _refresh_and_rebind():
            # Refresh MCP (new client + toolkit) and rebind tools into the model.
            # MCPRuntime handles snapshot logging + safe old-client close.
            self.model = await self.mcp.refresh_and_bind(self.model)

        tools_node = make_resilient_tools_node(
            get_tools=self.mcp.get_tools,  # always returns the latest tool instances
            refresh_cb=_refresh_and_rebind,  # on timeout/401/stream close, refresh + rebind
        )
        builder.add_node("tools", tools_node)
        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")

        return builder

    async def reasoner(self, state: MessagesState):
        """
        Single LLM step that may trigger MCP tool calls. After tools run,
        we parse ToolMessage payloads (JSON array) as List[VectorSearchHit] and attach to metadata.
        """
        if self.model is None:
            raise RuntimeError(
                "Model is not initialized. Did you forget to call async_init()?"
            )

        try:
            response = self.model.invoke([self.base_prompt] + state["messages"])

            collected_hits: List[VectorSearchHit] = []
            saw_tool_msg = False

            for msg in state["messages"]:
                if (
                    isinstance(msg, ToolMessage)
                    and getattr(msg, "name", "")
                    == "search_documents_using_vectorization"
                ):
                    saw_tool_msg = True

                    # Minimal parse: accept list/dict directly, else parse JSON string
                    data = (
                        msg.content
                        if isinstance(msg.content, (list, dict))
                        else json.loads(msg.content)
                    )

                    try:
                        hits = self._hits_adapter.validate_python(
                            data
                        )  # List[VectorSearchHit]
                        collected_hits.extend(hits)
                    except ValidationError as ve:
                        logger.error(
                            "Dominic: tool payload failed VectorSearchHit validation: %s",
                            ve,
                        )

            if saw_tool_msg and not collected_hits:
                ai_message = await self.model.ainvoke(
                    [
                        HumanMessage(
                            content="I tried to retrieve documents but couldn't process the results. Please try again."
                        )
                    ]
                )
                return {"messages": [ai_message]}

            if collected_hits:
                existing = response.response_metadata.get("sources", [])
                response.response_metadata["sources"] = existing + [
                    h.model_dump() for h in collected_hits
                ]

            return {"messages": [response]}

        except Exception as e:
            logger.exception("Dominic: unexpected error: %s", e)
            error_message = await self.model.ainvoke(
                [
                    HumanMessage(
                        content="An error occurred while processing your request. Please try again later."
                    )
                ]
            )
            return {"messages": [error_message]}

    # --- helpers -------------------------------------------------------------

    def _validate_hits(self, payload) -> List[VectorSearchHit]:
        """
        Accepts the tool JSON payload and validates it as List[VectorSearchHit].
        The MCP endpoint is expected to return VectorSearchHit dicts directly.
        """
        if not isinstance(payload, list):
            raise ValidationError.from_exception_data(
                title="VectorSearchHit list expected",
                line_errors=[],
            )
        return self._hits_adapter.validate_python(payload)
