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

from fastapi import APIRouter, Depends, status
from fred_core import KeycloakUser, get_current_user
from pydantic import BaseModel, Field

from agentic_backend.application_context import get_feedback_store
from agentic_backend.core.feedback.feedback_service import FeedbackService
from agentic_backend.core.feedback.feedback_structures import FeedbackRecord

logger = logging.getLogger(__name__)

# Create a module-level APIRouter
router = APIRouter(tags=["Feedback"])


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
# Dependencies
# ----------------------------------------------------------------------
def get_feedback_service() -> FeedbackService:
    """Dependency function to get the feedback service instance."""
    return FeedbackService(get_feedback_store())


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------
@router.post(
    "/chatbot/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Submit feedback for a chatbot response",
)
async def post_feedback(
    payload: FeedbackPayload,
    user: KeycloakUser = Depends(get_current_user),
    service: FeedbackService = Depends(get_feedback_service),
):
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
    await service.add_feedback(user, feedback_record)
    return  # implicit 204


@router.get(
    "/chatbot/feedback",
    response_model=List[FeedbackRecord],
    summary="List all feedback entries",
)
async def get_feedback(
    user: KeycloakUser = Depends(get_current_user),
    service: FeedbackService = Depends(get_feedback_service),
):
    return await service.get_feedback(user)


@router.delete(
    "/chatbot/feedback/{feedback_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a feedback entry by ID",
)
async def delete_feedback(
    feedback_id: str,
    user: KeycloakUser = Depends(get_current_user),
    service: FeedbackService = Depends(get_feedback_service),
):
    await service.delete_feedback(user, feedback_id)
    return  # implicit 204
