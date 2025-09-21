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

from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from app.common.structures import MCPServerConfiguration


class BaseAgentRequest(BaseModel):
    agent_type:  Literal["mcp"]  # , "rag", "custom"]  # extendable in future

class MCPAgentRequest(BaseAgentRequest):
    type: Literal["mcp"]
    name: str
    base_prompt: str
    mcp_servers: List[MCPServerConfiguration]
    role: str
    description: str
    icon: Optional[str] = None
    categories: Optional[List[str]] = None
    tag: Optional[str] = None


# In the future, other types:
# class RagAgentRequest(BaseAgentRequest):
#     agent_type: Literal["rag"]
#     ...

CreateAgentRequest = Annotated[
    Union[MCPAgentRequest], Field(discriminator="agent_type")
]
