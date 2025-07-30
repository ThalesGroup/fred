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

import uuid
from datetime import datetime
from typing import List, Dict, Optional

from app.core.feedback.store.base_feedback_store import BaseFeedbackStore


class FeedbackService:
    """
    Service for storing, retrieving, and deleting structured user feedback entries.
    Supports any backend that implements BaseFeedbackStore.
    """

    def __init__(self, store: BaseFeedbackStore):
        self.store = store

    def get_feedback(self) -> List[Dict]:
        """
        Returns all feedback entries stored.
        """
        return self.store.list()

    def add_feedback(self, feedback: Dict) -> Dict:
        """
        Adds a new feedback entry with a UUID and timestamp.
        """
        feedback_id = str(uuid.uuid4())
        entry = {
            **feedback,
            "id": feedback_id,
            "created_at": datetime.utcnow().isoformat(),
        }
        self.store.save(entry)
        return entry

    def delete_feedback(self, feedback_id: str) -> bool:
        """
        Deletes a feedback entry by ID.
        Returns True if the entry was deleted, False if it was not found.
        """
        return self.store.delete(feedback_id)

    def get_feedback_by_id(self, feedback_id: str) -> Optional[Dict]:
        """
        Returns a single feedback entry by ID, or None if not found.
        """
        return self.store.get(feedback_id)
