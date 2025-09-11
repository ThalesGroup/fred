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

from abc import abstractmethod
from datetime import datetime
import logging
from typing import List, Optional, Sequence

from IPython.display import Image
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph
from langchain_core.messages import SystemMessage, BaseMessage
from app.common.structures import AgentSettings
from app.core.agents.agent_state import Prepared, resolve_prepared
from app.application_context import get_knowledge_flow_base_url
from app.core.agents.runtime_context import RuntimeContext

logger = logging.getLogger(__name__)


# class Flow:
#     def __init__(self, name: str, description: str, graph: StateGraph):
#         # Name of agentic flow.
#         self.name: str = name
#         # Description of agentic flow.
#         self.description: str = description
#         # The graph of the agentic flow.
#         self.graph: StateGraph | None = graph
#         self.streaming_memory: MemorySaver = MemorySaver()
#         self.compiled_graph: CompiledStateGraph | None = None
#         self.runtime_context: Optional[RuntimeContext] = None

#     def get_compiled_graph(self) -> CompiledStateGraph:
#         if not self.graph:
#             raise ValueError("Graph is not defined.")
#         return self.graph.compile(checkpointer=self.streaming_memory)

#     def save_graph_image(self, path: str):
#         if not self.graph:
#             raise ValueError("Graph is not defined.")
#         compiled_graph: CompiledStateGraph = self.graph.compile()
#         graph = Image(compiled_graph.get_graph().draw_mermaid_png())
#         with open(f"{path}/{self.name}.png", "wb") as f:
#             f.write(graph.data)

#     def set_runtime_context(self, context: RuntimeContext) -> None:
#         self.runtime_context = context

#     def get_runtime_context(self) -> Optional[RuntimeContext]:
#         return self.runtime_context

#     def __str__(self) -> str:
#         return f"{self.name}: {self.description}"


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

    def __init__(self, agent_settings: AgentSettings):
        """
        Initialize an AgentFlow instance with configuration from AgentSettings.

        This sets all primary properties of the agent according to the provided AgentSettings,
        falling back to class defaults if not explicitly specified.
        Args:
            agent_settings: An AgentSettings instance containing agent metadata, display, and configuration options.
                - name: The name of the agent.
                - role: The agent's primary role or persona.
                - nickname: Alternate short label for UI display.
                - description: A detailed summary of agent functionality.
                - icon: The icon used for representation in the UI.
                - categories: (Optional) Categories that the agent is part of.
                - tag: (Optional) Short tag identifier for the agent.
        """

        self.agent_settings = agent_settings
        self.name = agent_settings.name
        self.nickname = agent_settings.nickname or agent_settings.name
        self.role = (
            agent_settings.role
            if agent_settings.role is not None
            else self.__class__.role
        )
        self.description = (
            agent_settings.description
            if agent_settings.description is not None
            else self.__class__.description
        )
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.categories = (
            agent_settings.categories
            if agent_settings.categories is not None
            else self.__class__.categories
        )
        self.tag = (
            agent_settings.tag if agent_settings.tag is not None else self.__class__.tag
        )
        self.model = None  # Will be set in async_init
        self.base_prompt = ""  # Will be set in async_init
        self._graph = None  # Will be built in async_init
        self.streaming_memory = MemorySaver()
        self.compiled_graph: Optional[CompiledStateGraph] = None
        self.runtime_context: Optional[RuntimeContext] = None

    def use_fred_prompts(self, messages: Sequence[BaseMessage]) -> List[BaseMessage]:
        """
        Apply the prompts/templates the user picked in the Fred UI to this turn as ONE system message.

        What you get
        - End-to-end prompt management: respects the user's selections from the chat UI.
        - Order preserved: prompts/templates are combined in the same order the user chose.
        - Consistent formatting: merged into a single SystemMessage, followed by the agent's base prompt.
        - Server-side control: fetched and composed on the server for auditability and safety.

        When to use
        - Any agent that should honor the user's prompt/template selections from the Fred UI.

        Guarantees
        - If nothing is selected: returns `messages` unchanged.
        - If selections exist: prepends one `SystemMessage` built from the UI selections + this agent's `base_prompt`.
        - No custom graph/state required; this is an opt-in helper.

        Args:
            messages: The conversation messages to send to the model.

        Returns:
            A new list of messages (possibly with a leading `SystemMessage`).
        """
        sys_text = self._compose_fred_system_text().strip()
        if not sys_text:
            return list(messages)
        return [SystemMessage(content=sys_text), *messages]

    def _compose_fred_system_text(self) -> str:
        """
        Internal: builds the system text from (a) selected Fred resources and
        (b) this agent's base_prompt, preserving order and keeping it in one message.
        """
        ctx = self.get_runtime_context() or RuntimeContext()
        prepared: Prepared = resolve_prepared(ctx, get_knowledge_flow_base_url())

        pre_text = (prepared.prompt_text or "").strip()
        base_text = (self.base_prompt or "").strip()
        if pre_text and base_text:
            return f"{pre_text}\n\n{base_text}"
        return pre_text or base_text

    def get_compiled_graph(self) -> CompiledStateGraph:
        """
        Compile and return the agent's graph.
        This method is idempotent and reuses the cached compiled graph.
        """
        if self.compiled_graph is None:
            self.compiled_graph = self._graph.compile(
                checkpointer=self.streaming_memory
            )
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

    @abstractmethod
    async def async_init(self):
        """
        Asynchronous initialization routine that must be implemented by subclasses.
        """
        pass
