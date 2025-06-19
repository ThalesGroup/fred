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

from typing import Optional
from IPython.display import Image
import logging
from langgraph.graph import MessagesState
from langgraph.graph.state import CompiledStateGraph, StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.tools import BaseToolkit
from langchain_core.messages import SystemMessage


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

    def __str__(self) -> str:
        return f"{self.name}: {self.description}"

class AgentFlow:
    """
    Represents a specialized LangGraph agent.

    Key Concepts:
    - Agents are stateful flows that use an LLM to make decisions or return outputs.
    - Each agent can optionally use LangChain Toolkits to invoke external tools.
    - A compiled LangGraph is built from a `StateGraph` which defines logic via nodes and edges.

    Typical Usage:
    - Subclass this to create a domain-specific expert (e.g., MonitoringExpert).
    - Define a graph (flow), a base prompt, and optional tools.
    - Use the built-in `reasoner()` to implement the thinking node.
    
    Attributes:
        name (str): The name of the agent.
        role (str): The role of the agent.
        nickname (str): The nickname of the agent.
        description (str): A description of the agent's functionality.
        icon (str): An icon reference for the agent.
        graph: The agent's state graph.
        base_prompt (str): The base prompt used by the agent.
        categories (list): Categories the agent belongs to.
        tag (str): Tag for the agent.
        toolkit: the agent toolkit
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
        cluster_fullname: Optional[str] = None,
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
        self.compiled_graph = None
        self._context_enrichment = None
        self.toolkit = toolkit
        self.cluster_fullname = cluster_fullname
        # Import here to avoid circular import
        from fred.application_context import get_model_for_agent
        self.model = get_model_for_agent(self.name)
        if self.toolkit:
            self.model = self.model.bind_tools(self.toolkit.get_tools())
    
    def get_tools(self):
        return self.toolkit.get_tools() if self.toolkit else []
    
    def get_compiled_graph(self) -> CompiledStateGraph:
        """
        Compile and return the agent's graph.
        
        Returns:
            The compiled state graph ready for execution.
        """
        if self.compiled_graph is None:
            self.compiled_graph = self.graph.compile(checkpointer=self.streaming_memory)
        return self.compiled_graph
    
    async def expert(self, state):
        """
        Processes user messages and interacts with the model.
        Uses context enrichment if available.
        
        Args:
            state: The current state of the conversation.
            
        Returns:
            dict: The updated state with the expert's response.
        """
        
        # Build prompt including context enrichment if available
        prompt_content = self.base_prompt
        if self._context_enrichment:
            prompt_content = f"{self.base_prompt}\n\n{self._context_enrichment}"
            logger.info(f"Agent '{self.name}' using enriched prompt with context")
            # Log a short preview of the prompt (first 100 chars)
            preview = prompt_content[:100].replace('\n', ' ') + "..."
            logger.debug(f"Prompt preview: {preview}")
        else:
            logger.info(f"Agent '{self.name}' using standard prompt without context")
            
        prompt = SystemMessage(content=prompt_content)
        response = await self.model.ainvoke([prompt] + state["messages"])
        return {"messages": [response]}
    
    def set_context_enrichment(self, context_text: str):
        """
        Temporarily sets a context enrichment for this agent.
        
        Args:
            context_text: The formatted context text to add to the base prompt.
        """
        self._context_enrichment = context_text
        logger.info(f"Temporary context added to agent '{self.name}'")
        
    def clear_context_enrichment(self):
        """
        Removes the temporary context enrichment.
        """
        if self._context_enrichment:
            logger.info(f"Cleaning up temporary context for agent '{self.name}'")
            self._context_enrichment = None
    
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

    def __str__(self) -> str:
        """String representation of the agent."""
        return f"{self.name} ({self.nickname}): {self.description}"
    
    async def reasoner(self, state: MessagesState):
        prompt_content = self.base_prompt
        if self._context_enrichment:
            prompt_content += f"\n\n{self._context_enrichment}"
            logger.info(f"[{self.name}] Using enriched prompt with context.")
        else:
            logger.info(f"[{self.name}] Using standard prompt.")

        prompt = SystemMessage(content=prompt_content)
        response = await self.model.ainvoke([prompt] + state["messages"])
        return {"messages": [response]}


