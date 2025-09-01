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

from langgraph.graph import START, END, MessagesState, StateGraph
from app.common.structures import AgentSettings
from app.core.model.model_factory import get_model
from app.core.agents.flow import AgentFlow

logger = logging.getLogger(__name__)


class GeneralistExpert(AgentFlow):
    """
    Generalist Expert provides guidance on a wide range of topics
    without deep specialization.
    """

    # Class-level metadata
    name: str
    role: str
    nickname: str
    description: str
    icon: str = "generalist_agent"
    tag: str = "Generalist"

    def __init__(self, agent_settings: AgentSettings):
        self.agent_settings = agent_settings
        self.name = agent_settings.name
        self.nickname = agent_settings.nickname or agent_settings.name
        self.role = agent_settings.role
        self.description = agent_settings.description
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.categories = agent_settings.categories or ["General"]
        self.model = None  # Will be set in async_init
        self.base_prompt = ""  # Will be set in async_init
        self._graph = None  # Will be built in async_init

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
        today = datetime.now().strftime("%Y-%m-%d")
        return "\n".join(
            [
                "You are a friendly generalist expert, skilled at providing guidance on a wide range of topics without deep specialization.",
                "Your role is to respond with clarity, providing accurate and reliable information.",
                "When appropriate, highlight elements that could be particularly relevant.",
                f"The current date is {today}.",
                "In case of graphical representation, render mermaid diagrams code.",
            ]
        )

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)
        builder.add_node("expert", self.reasoner)
        builder.add_edge(START, "expert")
        builder.add_edge("expert", END)
        return builder

    async def reasoner(self, state: MessagesState):
        messages = self.use_fred_prompts(state["messages"])
        assert self.model is not None
        response = await self.model.ainvoke(messages)
        return {"messages": [response]}
