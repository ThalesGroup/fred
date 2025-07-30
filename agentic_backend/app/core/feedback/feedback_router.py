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


# import logging

# logger = logging.getLogger(__name__)

# Define a Pydantic model for the feedback payload
# class FeedbackPayload(BaseModel):
#     rating: int
#     reason: str
#     feedbackType: str  # Could use Literal['up', 'down'] for stricter typing
#     messageId: str | None = None

# router = APIRouter()


# Base = declarative_base()

# class Feedback(Base):
#     __tablename__ = 'feedback'

#     id = Column(Integer, primary_key=True, index=True)
#     user = Column(String, index=True)
#     rating = Column(Integer, nullable=False)
#     reason = Column(String, nullable=True)
#     feedback_type = Column(String, nullable=False)
#     message_id = Column(String, nullable=True)
#     timestamp = Column(DateTime, default=datetime.utcnow)

# @router.post("/fred/feedback", tags=["Feedback"], summary="Submit user feedback")
# async def post_feedback(
#     feedback: FeedbackPayload,
#     user: KeycloakUser = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     logger.info(f"Feedback received from {user.username}: {feedback}")

#     TODO FEEDBACK
#     Create a new feedback record
#     new_feedback = Feedback(
#        user=user.username,
#        rating=feedback.rating,
#        reason=feedback.reason,
#        feedback_type=feedback.feedbackType,
#        message_id=feedback.messageId,
#        timestamp=datetime.utcnow(),
#     )
#     db.add(new_feedback)
#     db.commit()
#     db.refresh(new_feedback)

#     return {"success": True, "feedback_id": new_feedback.id}
