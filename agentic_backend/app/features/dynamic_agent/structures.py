from pydantic import BaseModel, Field
from typing import Literal, List, Optional, Union
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

CreateAgentRequest = Union[MCPAgentRequest]
