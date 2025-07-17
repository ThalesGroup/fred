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

from app.features.feedback.feedback_service import FeedbackService
from app.features.feedback.store.local_feedback_store import LocalFeedbackStore
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from app.common.structure import FeedbackStorageConfig
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

class FeedbackPayload(BaseModel):
    rating: int
    comment: Optional[str] = None
    message_id: str = Field(..., alias="messageId")
    session_id: str = Field(..., alias="sessionId")
    agent_name: str = Field(..., alias="agentName")

    class Config:
        populate_by_name = True

class FeedbackController:
    def __init__(self, router: APIRouter, config: FeedbackStorageConfig):
        if config.type == "local":
            store = LocalFeedbackStore(config.local_path)
        else:
            raise NotImplementedError(f"Feedback storage type '{config.type}' is not implemented yet.")
        self.service = FeedbackService(store)

        @router.post("/chatbot/feedback", tags=["Feedback"])
        def post_feedback(feedback: FeedbackPayload):
            logger.info(f"Feedback received: {feedback}")
            created = self.service.add_feedback(feedback.model_dump(by_alias=True))
            return {"success": True, "feedback": created}

        @router.get("/chatbot/feedback", tags=["Feedback"])
        def get_feedback():
            return self.service.get_feedback()

        @router.delete("/chatbot/feedback/{feedback_id}", tags=["Feedback"])
        def delete_feedback(feedback_id: str):
            deleted = self.service.delete_feedback(feedback_id)
            if not deleted:
                raise HTTPException(status_code=404, detail="Feedback entry not found")
            return {"message": f"Entry {feedback_id} deleted"}
