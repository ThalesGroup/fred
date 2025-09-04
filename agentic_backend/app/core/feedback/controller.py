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

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fred_core import KeycloakUser, get_current_user
from pydantic import BaseModel, Field

from app.application_context import get_feedback_store
from app.core.feedback.service import FeedbackService
from app.core.feedback.structures import FeedbackRecord

logger = logging.getLogger(__name__)
router = APIRouter()


# ----------------------------------------------------------------------
# Payload received from frontend
# ----------------------------------------------------------------------
class FeedbackPayload(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None
    message_id: str = Field(..., alias="messageId")
    session_id: str = Field(..., alias="sessionId")
    agent_name: str = Field(..., alias="agentName")

    class Config:
        populate_by_name = True


# ----------------------------------------------------------------------
# FeedbackController
# ----------------------------------------------------------------------
class FeedbackController:
    def __init__(self, router: APIRouter):
        self.service = FeedbackService(get_feedback_store())

        def handle_exception(e: Exception) -> HTTPException:
            logger.error(f"[FEEDBACK] Internal error: {e}", exc_info=True)
            return HTTPException(status_code=500, detail="Internal server error")

        self._register_routes(router, handle_exception)

    def _register_routes(self, router: APIRouter, handle_exception):
        @router.post(
            "/chatbot/feedback",
            tags=["Feedback"],
            status_code=status.HTTP_204_NO_CONTENT,
            summary="Submit feedback for a chatbot response",
        )
        async def post_feedback(
            payload: FeedbackPayload,
            user: KeycloakUser = Depends(get_current_user),
        ):
            try:
                feedback_record = FeedbackRecord(
                    id=str(uuid.uuid4()),
                    session_id=payload.session_id,
                    message_id=payload.message_id,
                    agent_name=payload.agent_name,
                    rating=payload.rating,
                    comment=payload.comment,
                    created_at=datetime.utcnow(),
                    user_id=user.uid,
                )
                self.service.add_feedback(feedback_record)
                return  # implicit 204
            except Exception as e:
                raise handle_exception(e)

        @router.get(
            "/chatbot/feedback",
            response_model=List[FeedbackRecord],
            tags=["Feedback"],
            summary="List all feedback entries",
        )
        async def get_feedback(_: KeycloakUser = Depends(get_current_user)):
            try:
                return self.service.get_feedback()
            except Exception as e:
                raise handle_exception(e)

        @router.delete(
            "/chatbot/feedback/{feedback_id}",
            tags=["Feedback"],
            status_code=status.HTTP_204_NO_CONTENT,
            summary="Delete a feedback entry by ID",
        )
        async def delete_feedback(
            feedback_id: str, _: KeycloakUser = Depends(get_current_user)
        ):
            try:
                deleted = self.service.delete_feedback(feedback_id)
                if not deleted:
                    raise HTTPException(
                        status_code=404, detail="Feedback entry not found"
                    )
                return  # implicit 204
            except Exception as e:
                raise handle_exception(e)
