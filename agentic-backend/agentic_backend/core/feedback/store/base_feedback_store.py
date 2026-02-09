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
from typing import List

from agentic_backend.core.feedback.feedback_structures import FeedbackRecord


class BaseFeedbackStore(ABC):
    @abstractmethod
    async def list(self) -> List[FeedbackRecord]:
        """Return all feedback entries as a list of dictionaries."""
        pass

    @abstractmethod
    async def get(self, feedback_id: str) -> FeedbackRecord | None:
        """Retrieve a single feedback entry by ID."""
        pass

    @abstractmethod
    async def save(self, feedback: FeedbackRecord) -> None:
        """Save or update a feedback entry."""
        pass

    @abstractmethod
    async def delete(self, feedback_id: str) -> None:
        """Delete a feedback entry by ID."""
        pass
