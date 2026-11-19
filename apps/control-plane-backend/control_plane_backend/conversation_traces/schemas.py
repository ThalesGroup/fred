# Copyright Thales 2026
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

from fred_core.conversation_trace import TraceAvailability, TraceOutcome
from pydantic import BaseModel, ConfigDict


class ConversationTraceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class ConversationTraceSummary(BaseModel):
    session_id: str
    agent_display_name: str
    team_id: str
    latest_started_at: datetime
    outcome: TraceOutcome
    availability: TraceAvailability


class ConversationTraceCatalog(BaseModel):
    conversations: list[ConversationTraceSummary]
    next_cursor: str | None


class ConversationTraceTurn(BaseModel):
    exchange_id: str
    turn_number: int | None
    started_at: datetime
    duration_ms: int | None
    outcome: TraceOutcome
    availability: TraceAvailability
    call_ids: list[str]
    trace_id: str | None
    span_id: str | None


class ConversationTraceDetail(BaseModel):
    session_id: str
    agent_display_name: str
    team_id: str
    turns: list[ConversationTraceTurn]
    next_cursor: str | None
