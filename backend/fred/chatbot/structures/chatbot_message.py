from typing import Optional

from pydantic import BaseModel, Field

from services.chatbot_session.structure.chat_schema import SessionSchema
from chatbot.structures.agentic_flow import AgenticFlow


class ChatBotEventConfiguration(BaseModel):
    """
    The configuration of the chatbot message
    """
    session_id: str = Field(description="The unique ID of the chatbot")
    agentic_flow: Optional[AgenticFlow] = Field(
        default=None, description="The agentic flow of the chatbot"
    )
    cluster_name: Optional[str] = Field(
        default=None, description="The cluster name of the chatbot"
    )

class ChatAskInput(BaseModel):
    user_id: str
    session_id: Optional[str] = None
    message: str
    agent_name: str

class ChatBotEvent(BaseModel):
    """
    LEGACY The event of the chatbot
    """

    configuration: ChatBotEventConfiguration = Field(
        description="The configuration of the chatbot message"
    )
    messages: list[dict] = Field(description="The messages of the chatbot")
