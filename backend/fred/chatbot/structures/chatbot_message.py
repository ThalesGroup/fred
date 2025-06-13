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
    argument: Optional[str]
    chat_profile_id: Optional[str] = None

class ChatBotEvent(BaseModel):
    """
    LEGACY The event of the chatbot
    """

    configuration: ChatBotEventConfiguration = Field(
        description="The configuration of the chatbot message"
    )
    messages: list[dict] = Field(description="The messages of the chatbot")
