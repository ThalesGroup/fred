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

from datetime import datetime
from typing import Optional

from fred_core import BaseModelWithId
from pydantic import ConfigDict, Field


class FeedbackRecord(BaseModelWithId):
    session_id: str = Field(..., description="Session ID associated with the feedback")
    message_id: str = Field(..., description="Message ID the feedback refers to")
    agent_id: str = Field(
        ..., description="Name of the agent that generated the message"
    )
    rating: int = Field(..., ge=1, le=5, description="User rating, typically 1–5 stars")
    comment: Optional[str] = Field(
        None, description="Optional user comment or clarification"
    )
    created_at: datetime = Field(
        ..., description="Timestamp when the feedback was submitted"
    )
    user_id: str = Field(..., description="Optional user ID if identity is tracked")

    # Pydantic v2 configuration
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "id": "fbk_abc123",
                "session_id": "sess_xyz789",
                "message_id": "msg_001",
                "agent_id": "123456",
                "rating": 4,
                "comment": "Helpful but a bit long",
                "created_at": "2025-08-06T12:00:00Z",
                "user_id": "user_456",
            }
        },
    )
