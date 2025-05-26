from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from feedback.feedback_service import FeedbackService
from feedback.store.local_feedback_store import LocalFeedbackStore
from feedback.setting.feedback_store_local_settings import FeedbackStoreLocalSettings
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
    def __init__(self, router: APIRouter):
        settings = FeedbackStoreLocalSettings()
        store = LocalFeedbackStore(settings.root_path)
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
