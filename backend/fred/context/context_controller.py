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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from fred.context.context_service import ContextService

class ContextEntry(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None

class ContextController:
    def __init__(self, router: APIRouter):
        self.context_service = ContextService()

        @router.get("/context/{agent_id}")
        def get_context(agent_id: str):
            context = self.context_service.get_context(agent_id)
            return {"agent_id": agent_id, "context": context or {}}

        @router.post("/context/{agent_id}")
        def add_context(agent_id: str, entry: ContextEntry):
            entry_data = entry.model_dump()
            created = self.context_service.add_context(agent_id, entry_data)
            return created

        @router.delete("/context/{agent_id}/{context_id}")
        def delete_context_entry(agent_id: str, context_id: str):
            deleted = self.context_service.delete_context_entry(agent_id, context_id)
            if not deleted:
                raise HTTPException(status_code=404, detail="Context entry not found")
            return {"message": f"Entry {context_id} deleted from agent {agent_id}"}
