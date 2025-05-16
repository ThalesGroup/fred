from typing import Optional

from pydantic import BaseModel, Field


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
