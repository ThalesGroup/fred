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
