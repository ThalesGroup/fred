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

from typing import List

from fred_core import Action, KeycloakUser, Resource, authorize

from app.core.feedback.store.base_feedback_store import BaseFeedbackStore
from app.core.feedback.structures import FeedbackRecord


class FeedbackService:
    """
    Service for storing, retrieving, and deleting structured user feedback entries.
    Supports any backend that implements BaseFeedbackStore.
    """

    def __init__(self, store: BaseFeedbackStore):
        self.store = store

    @authorize(action=Action.READ, resource=Resource.FEEDBACK)
    def get_feedback(self, user: KeycloakUser) -> List[FeedbackRecord]:
        """
        Returns all feedback entries stored.
        """
        return self.store.list()

    @authorize(action=Action.CREATE, resource=Resource.FEEDBACK)
    def add_feedback(self, user: KeycloakUser, feedback: FeedbackRecord) -> None:
        """
        Adds a new feedback entry with a UUID and timestamp.
        """
        self.store.save(feedback)

    @authorize(action=Action.DELETE, resource=Resource.FEEDBACK)
    def delete_feedback(self, user: KeycloakUser, feedback_id: str) -> None:
        """
        Deletes a feedback entry by ID.
        Returns True if the entry was deleted, False if it was not found.
        """
        self.store.delete(feedback_id)

    @authorize(action=Action.READ, resource=Resource.FEEDBACK)
    def get_feedback_by_id(
        self, user: KeycloakUser, feedback_id: str
    ) -> FeedbackRecord | None:
        """
        Returns a single feedback entry by ID, or None if not found.
        """
        return self.store.get(feedback_id)
