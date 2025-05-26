
from pathlib import Path
import os

class FeedbackStoreLocalSettings:
    def __init__(self):
        env_value = os.getenv("LOCAL_FEEDBACK_STORAGE_PATH")
        if env_value:
            self.root_path = Path(env_value)
        else:
            self.root_path = Path.home() / ".fred" / "knowledge" / "feedback-store"

        self.root_path.mkdir(parents=True, exist_ok=True)
