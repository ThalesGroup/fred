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

import os
import json
from typing import Optional
from app.feedback.store.base_feedback_store import BaseFeedbackStore

class LocalFeedbackStore(BaseFeedbackStore):
    def __init__(self, root_path: str):
        self.root_path = os.path.expanduser(root_path)
        os.makedirs(self.root_path, exist_ok=True)

    def _file_path(self, key: str) -> str:
        return os.path.join(self.root_path, f"{key}.json")

    def get_feedback(self, key: str) -> Optional[str]:
        try:
            with open(self._file_path(key), "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return None

    def set_feedback(self, key: str, feedback: str) -> None:
        with open(self._file_path(key), "w", encoding="utf-8") as f:
            f.write(feedback)

    def delete_feedback(self, key: str) -> None:
        try:
            os.remove(self._file_path(key))
        except FileNotFoundError:
            pass
