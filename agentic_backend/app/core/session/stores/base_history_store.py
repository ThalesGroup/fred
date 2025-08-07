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

from typing import List, Dict
from abc import ABC, abstractmethod

from app.core.chatbot.chat_schema import (
    ChatMessagePayload,
)
from app.core.chatbot.metric_structures import MetricsResponse


class BaseHistoryStore(ABC):

    @abstractmethod
    def save(
        self, session_id: str, messages: List[ChatMessagePayload], user_id: str
    ) -> None:
        """Save a batch of messages to the session history."""
        pass

    @abstractmethod
    def get(
        self, session_id: str,
    ) -> List[ChatMessagePayload]:
        """Retrieve messages for a given session."""
        pass

    @abstractmethod
    def get_metrics(
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
