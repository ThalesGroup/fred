import os
import json
from typing import Optional
from fred.feedback.store.base_feedback_store import BaseFeedbackStore

class LocalFeedbackStore(BaseFeedbackStore):
    def __init__(self, root_path: str):
        self.root_path = root_path
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
