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

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SessionSchema(BaseModel):
    """Shared session schema used by agentic-backend (write) and control-plane (read/delete)."""

    id: str
    user_id: str
    team_id: str | None = None
    agent_id: str | None = None
    title: str
    updated_at: datetime
    next_rank: int | None = None
    preferences: dict[str, Any] | None = None
