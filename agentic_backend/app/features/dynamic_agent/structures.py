from pydantic import BaseModel, Field
from typing import Literal, List, Optional, Union

# Base class with discriminator
class BaseAgentRequest(BaseModel):
    agent_type: str = Field(..., description="The type of agent to create (e.g., 'mcp', 'rag').")

# MCP agent subtype
class MCPAgentRequest(BaseAgentRequest):
    agent_type: Literal["mcp"]
    name: str
    prompt: str
    mcp_urls: List[str]
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

# Union for routing
CreateAgentRequest = Union[MCPAgentRequest]  # Add more types as you go
