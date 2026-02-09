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

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from agentic_backend.core.chatbot.chat_schema import (
    ChatMessage,
)
from agentic_backend.core.chatbot.metric_structures import MetricsResponse


class BaseHistoryStore(ABC):
    @abstractmethod
    async def save(
        self, session_id: str, messages: List[ChatMessage], user_id: str
    ) -> None:
        """Save a batch of messages to the session history."""
        pass

    @abstractmethod
    async def get(
        self,
        session_id: str,
    ) -> List[ChatMessage]:
        """Retrieve messages for a given session."""
        pass

    @abstractmethod
    async def get_chatbot_metrics(
        self,
        start: str,
        end: str,
        user_id: str,
        precision: str,
        groupby: List[str],
        agg_mapping: Dict[str, List[str]],
    ) -> MetricsResponse:
        """Retrieve messages for a given session."""
        pass

    @abstractmethod
    async def save_with_conn(
        self, conn: Any, session_id: str, messages: List[ChatMessage], user_id: str
    ) -> None:
        """
        Reuse an existing DB connection/transaction.
        """
        pass
