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

from context.store.context_storage_factory import get_context_store
import json
import uuid
from typing import Dict, Any

class ContextService:
    def __init__(self):
        self.store = get_context_store()

    def get_context(self, agent_id: str) -> Dict[str, Dict[str, Any]]:
        try:
            raw = self.store.get_context(agent_id)
            if raw is None:
                return {}
            return json.loads(raw)
        except Exception:
            return {}

    def add_context(self, agent_id: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        context = self.get_context(agent_id)
        entry_id = entry.get("id") or str(uuid.uuid4())
        # remove id from inside the object to avoid duplication
        entry = {k: v for k, v in entry.items() if k != "id"}
        context[entry_id] = entry
        serialized = json.dumps(context, ensure_ascii=False, indent=2)
        self.store.set_context(agent_id, serialized)
        return {"id": entry_id, **entry}

    def delete_context_entry(self, agent_id: str, context_id: str) -> bool:
        context = self.get_context(agent_id)
        if context_id not in context:
            return False
        del context[context_id]
        self.store.set_context(agent_id, json.dumps(context, ensure_ascii=False, indent=2))
        return True

