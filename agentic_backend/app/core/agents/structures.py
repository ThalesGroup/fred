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

from pydantic import BaseModel, Field
from typing import Literal, List, Optional, Union, Annotated
from app.common.structures import MCPServerConfiguration

class BaseAgentRequest(BaseModel):
    agent_type: str = Field(..., description="The type of agent to create (e.g., 'mcp', 'rag').")

class MCPAgentRequest(BaseAgentRequest):
    agent_type: Literal["mcp"]
    name: str
    base_prompt: str
    mcp_servers: List[MCPServerConfiguration]
    role: Optional[str] = None
    nickname: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    categories: Optional[List[str]] = None
    tag: Optional[str] = None

# In the future, other types:
# class RagAgentRequest(BaseAgentRequest):
#     agent_type: Literal["rag"]
#     ...

CreateAgentRequest = Annotated[
    Union[MCPAgentRequest],
    Field(discriminator="agent_type")
]

class AgenticFlow(BaseModel):
    """
    Agentic flow structure
    """

    name: str = Field(description="Name of the agentic flow")
    role: str = Field(description="Human-readable role of the agentic flow")
    nickname: Optional[str] = Field(
        description="Human-readable nickname of the agentic flow"
    )
    description: str = Field(
        description="Human-readable description of the agentic flow"
    )
    icon: Optional[str] = Field(description="Icon of the agentic flow")
    experts: Optional[list[str]] = Field(
        description="List of experts in the agentic flow"
    )
    tag: Optional[str] = Field(description="Human-readable tag of the agentic flow")
