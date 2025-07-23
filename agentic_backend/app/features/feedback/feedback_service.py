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
import json

from app.features.feedback.store.base_feedback_store import BaseFeedbackStore

class FeedbackService:
    def __init__(self, store: BaseFeedbackStore):
        self.store = store
        self._storage_key = "global_feedback"

    def get_feedback(self) -> dict:
        raw = self.store.get_feedback(self._storage_key)
        return json.loads(raw) if raw else {}

    def add_feedback(self, feedback: dict) -> dict:
        all_feedback = self.get_feedback()
        feedback_id = str(uuid.uuid4())
        entry = {**feedback, "id": feedback_id}
        all_feedback[feedback_id] = entry
        self.store.set_feedback(self._storage_key, json.dumps(all_feedback, indent=2, ensure_ascii=False))
        return entry

    def delete_feedback(self, feedback_id: str) -> bool:
        all_feedback = self.get_feedback()
        if feedback_id not in all_feedback:
            return False
        del all_feedback[feedback_id]
        self.store.set_feedback(self._storage_key, json.dumps(all_feedback, indent=2, ensure_ascii=False))
        return True
