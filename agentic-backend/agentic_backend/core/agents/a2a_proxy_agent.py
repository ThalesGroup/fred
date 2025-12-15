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

"""
Minimal stub AgentFlow used to register A2A proxy agents in the catalog.
This class is not executed for chat; routing is handled by the A2A bridge.
"""

from __future__ import annotations

from typing import ClassVar, Optional

from agentic_backend.common.structures import AgentChatOptions
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning
from agentic_backend.core.agents.runtime_context import RuntimeContext


class A2AProxyAgent(AgentFlow):
    tuning: ClassVar[AgentTuning] = AgentTuning(
        role="A2A",
        description="Routes messages to an external A2A agent.",
        tags=["a2a"],
    )
    default_chat_options: ClassVar[Optional[AgentChatOptions]] = AgentChatOptions()

    async def async_init(self, runtime_context: RuntimeContext):
        # No graph to build; routing is handled externally.
        self.runtime_context = runtime_context

    def get_compiled_graph(self):
        raise RuntimeError(
            "A2AProxyAgent does not run a LangGraph; routed via A2A bridge."
        )
