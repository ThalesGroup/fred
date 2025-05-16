from pydantic import BaseModel, Field


class ChatBotError(BaseModel):
    """
    The error of the chatbot
    """

    session_id: str | None = Field(
        default="None", description="The unique ID of the chatbot"
    )
    content: str = Field(default="None", description="The content of the error")
