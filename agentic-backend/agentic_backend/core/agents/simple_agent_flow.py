# app/core/agents/async_simple_expert_flow.py (REFACTORED BASE CLASS)

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


from __future__ import annotations

import logging
from typing import Any, Dict, Sequence, TypedDict

from langchain_core.messages import AIMessage, AnyMessage
from langgraph.constants import END, START
from langgraph.graph import StateGraph

from agentic_backend.core.agents.agent_flow import AgentFlow

logger = logging.getLogger(__name__)


# Minimal state for a simple expert (remains the same)
class SimpleExpertState(TypedDict):
    messages: Sequence[AnyMessage]


class SimpleAgentFlow(AgentFlow):
    """
    A base class for experts that run a single, ASYNCHRONOUS, non-graph logic
    (like a single LLM call).

    This class automatically builds a one-node LangGraph around the
    expert's 'arun' method to make it compatible with LangGraph orchestrators.

    Developers only need to implement the asynchronous 'arun' method.
    """

    # ------------------ Developer must override ------------------
    async def arun(self, *, messages: Sequence[AnyMessage]) -> AIMessage:
        """
        Core logic that runs the agent (MUST BE IMPLEMENTED BY SUBCLASSES).
        This is the ASYNCHRONOUS method.
        """
        raise NotImplementedError(
            "Subclasses must implement the asynchronous 'arun' method."
        )

    # ------------------ Internal Graph Logic ------------------

    # The graph structure itself remains identical, which is the part you wanted to keep.
    def _build_graph(self) -> StateGraph:
        """Builds the single-node graph required for orchestrator compatibility."""
        builder = StateGraph(SimpleExpertState)
        # Note: LangGraph nodes can be synchronous or asynchronous.
        builder.add_node("run_arun", self._run_arun_node)
        builder.add_edge(START, "run_arun")
        builder.add_edge("run_arun", END)
        return builder

    # The node is now an ASYNCHRONOUS method to correctly call 'arun'.
    async def _run_arun_node(self, state: SimpleExpertState) -> Dict[str, Any]:
        """LangGraph node that executes the asynchronous arun method."""

        logger.info(
            f"Simple expert {self.__class__.__name__} running asynchronous arun."
        )

        # ⭐️ We use 'await' to call the actual expert logic
        result_message = await self.arun(messages=state["messages"])

        logger.info(f"Simple expert {self.__class__.__name__} finished arun.")

        # Return state update: the new message is the result
        return {"messages": [result_message]}

    # ------------------ Lifecycle ------------------

    async def async_init(self):
        """Initializes the internal graph structure."""
        self._graph = self._build_graph()
        # Compile the graph so it can be streamed/invoked
        self.compiled = self._graph.compile()

    # We can also add a placeholder for synchronous calls to prevent accidental use
    def invoke(self, *args, **kwargs):
        raise NotImplementedError(
            "This agent is async-native (AsyncSimpleAgentFlow). Use 'astream_updates' or 'ainvoke'."
        )

    # ------------------ Utility to ensure AIMessage ------------------

    def ensure_aimessage(self, msg: object) -> AIMessage:
        """
        Guarantees the input is converted into a standard AIMessage object,
        ensuring compatibility with the SimpleAgentFlow's single-message contract.
        """
        # 1. Use the base utility to normalize to a BaseMessage (e.g., AIMessage)
        temp_message = self.ensure_any_message(
            msg
        )  # Assuming you removed the underscore

        # 2. Guarantee the type is AIMessage, stripping unnecessary fields if needed.
        # This handles the strict return type requirement of SimpleAgentFlow.
        if isinstance(temp_message, AIMessage):
            return temp_message

        # Fallback coercion: Convert any other BaseMessage into a guaranteed AIMessage.
        # This is safe because all BaseMessages have 'content' and 'additional_kwargs'.
        return AIMessage(
            content=temp_message.content,
            additional_kwargs=temp_message.additional_kwargs,
            # Note: response_metadata is often critical and should be preserved
            response_metadata=getattr(temp_message, "response_metadata", {}),
        )
