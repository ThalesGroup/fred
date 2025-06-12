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

import json
from pathlib import Path
from typing import Optional
from fred.context.store.base_context_store import BaseContextStore

class LocalContextStore(BaseContextStore):
    """
    Local context store implementation.
    Each agent's context is stored in a file named {agent_id}.json
    inside the configured directory.
    """
    def __init__(self, root_path: Path):
        self.root_path = Path(root_path).expanduser()
        self.root_path.mkdir(parents=True, exist_ok=True)

    def _get_agent_file(self, agent_id: str) -> Path:
        return self.root_path / f"{agent_id}.json"

    def get_context(self, agent_id: str) -> Optional[str]:
        path = self._get_agent_file(agent_id)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def set_context(self, agent_id: str, context: str) -> None:
        path = self._get_agent_file(agent_id)
        path.write_text(context, encoding="utf-8")

    def delete_context(self, agent_id: str) -> None:
        path = self._get_agent_file(agent_id)
        if path.exists():
            path.unlink()
