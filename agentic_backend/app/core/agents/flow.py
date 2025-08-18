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
from typing import List, Optional, Sequence, Literal

from IPython.display import Image
from langchain_core.tools import BaseToolkit
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph, StateGraph
from langchain_core.messages import SystemMessage, BaseMessage

from app.application_context import get_knowledge_flow_base_url
from app.core.agents.runtime_context import RuntimeContext
from app.core.agents.agent_state import resource_texts_by_kind

logger = logging.getLogger(__name__)


class Flow:
    """
    Represents a workflow with a graph.
    """

    def __init__(self, name: str, description: str, graph: StateGraph):
        # Name of agentic flow.
        self.name: str = name
        # Description of agentic flow.
        self.description: str = description
        # The graph of the agentic flow.
        self.graph: StateGraph | None = graph
        self.streaming_memory: MemorySaver = MemorySaver()
        self.compiled_graph: CompiledStateGraph | None = None
        self.runtime_context: Optional[RuntimeContext] = None

    def get_compiled_graph(self) -> CompiledStateGraph:
        """
        Compile and return the graph for execution.
        """
        if not self.graph:
            raise ValueError("Graph is not defined.")
        return self.graph.compile(checkpointer=self.streaming_memory)

    def save_graph_image(self, path: str):
        """
        Save the graph of agentic flow to an image.
        """
        if not self.graph:
            raise ValueError("Graph is not defined.")
        compiled_graph: CompiledStateGraph = self.graph.compile()
        graph = Image(compiled_graph.get_graph().draw_mermaid_png())
        with open(f"{path}/{self.name}.png", "wb") as f:
            f.write(graph.data)

    def set_runtime_context(self, context: RuntimeContext) -> None:
        """Set the runtime context for this flow."""
        self.runtime_context = context

    def get_runtime_context(self) -> Optional[RuntimeContext]:
        """Get the current runtime context."""
        return self.runtime_context

    def __str__(self) -> str:
        return f"{self.name}: {self.description}"


class AgentFlow:
    """
    Base class for LangGraph-based AI agents.

    Each agent is a stateful flow that uses a LangGraph to reason and produce outputs.
    Subclasses must define their graph (StateGraph), base prompt, and optionally a toolkit.

    Responsibilities:
    - Store metadata (name, role, etc.)
    - Hold a reference to the LangGraph (set via `graph`)
    - Compile the graph to run it
    - Optionally save it as an image (for visualization)

    Subclasses are responsible for defining any reasoning nodes (e.g. `reasoner`)
    and for calling `get_compiled_graph()` when they are ready to execute the agent.
    """

    # Class attributes for documentation/metadata
    name: str
    role: str
    nickname: str
    description: str
    icon: str
    tag: str

    def __init__(
        self,
        name: str,
        role: str,
        nickname: str,
        description: str,
        icon: str,
        graph,
        base_prompt: str,
        categories=None,
        tag=None,
        toolkit: BaseToolkit | None = None,
    ):
        """
        Initialize the agent with its core properties. This method creates the model,
        binds the toolkit if any.

        Args:
            name: The name of the agent.
            role: The role of the agent.
            nickname: The nickname of the agent.
            description: A description of the agent's functionality.
            icon: An icon reference for the agent.
            graph: The agent's state graph.
            base_prompt: The base prompt used by the agent.
            categories: Optional categories the agent belongs to.
            tag: Optional tag for the agent.
        """
        self.name = name
        self.role = role
        self.nickname = nickname
        self.description = description
        self.icon = icon
        self.graph = graph
        self.base_prompt = base_prompt
        self.categories = categories or []
        self.tag = tag
        self.streaming_memory = MemorySaver()
        self.compiled_graph: Optional[CompiledStateGraph] = None
        self.toolkit = toolkit
        self.runtime_context: Optional[RuntimeContext] = None

    def use_fred_resources(
        self,
        messages: Sequence[BaseMessage],
        kind: Literal["prompts", "templates", "all"] = "all",
    ) -> List[BaseMessage]:
        """
        Apply Fred resources (prompts, templates, or both) as ONE labeled system message.

        Args:
            messages: Existing conversation messages.
            kind: Which resources to include:
                - "prompts"   → only prompts
                - "templates" → only templates
                - "all"       → both prompts and templates

        Returns:
            New list of messages with a single SystemMessage prepended if resources exist.
        """
        sys_text = self._compose_fred_resource_text(kind).strip()
        if not sys_text:
            return list(messages)
        return [SystemMessage(content=sys_text), *messages]

    def _compose_fred_resource_text(self, kind: str = "all") -> str:
        """
        Compose system text from prompts, templates, or both (depending on `kind`).
        Preserves order and labels each section. Appends this agent's base_prompt at the end.
        """
        ctx = self.get_runtime_context() or RuntimeContext()
        kf_base = get_knowledge_flow_base_url()

        # Fetch prepared resource texts (already resolved + cleaned in agent_state)
        resources_by_kind = resource_texts_by_kind(ctx, kf_base)

        if kind != "all":
            # Restrict to one kind only
            resources_by_kind = {
                kind: resources_by_kind.get(kind, "")
            }

        parts = []
        for k, text in resources_by_kind.items():
            if text:
                parts.append(f"{k}:")
                parts.append(text)

        # Append the agent's base prompt
        if self.base_prompt and self.base_prompt.strip():
            parts.append(self.base_prompt.strip())

        return "\n\n".join(parts)

    def get_compiled_graph(self) -> CompiledStateGraph:
        """
        Compile and return the agent's graph.
        This method is idempotent and reuses the cached compiled graph.
        """
        if self.compiled_graph is None:
            self.compiled_graph = self.graph.compile(checkpointer=self.streaming_memory)
        return self.compiled_graph

    def save_graph_image(self, path: str):
        """
        Save the graph of the agent to an image.

        Args:
            path: Directory path where to save the image.
        """
        if not self.graph:
            raise ValueError("Graph is not defined.")
        compiled_graph = self.get_compiled_graph()
        graph = Image(compiled_graph.get_graph().draw_mermaid_png())
        with open(f"{path}/{self.name}.png", "wb") as f:
            f.write(graph.data)

    def set_runtime_context(self, context: RuntimeContext) -> None:
        """Set the runtime context for this agent."""
        self.runtime_context = context

    def get_runtime_context(self) -> Optional[RuntimeContext]:
        """Get the current runtime context."""
        return self.runtime_context

    def __str__(self) -> str:
        """String representation of the agent."""
        return f"{self.name} ({self.nickname}): {self.description}"
