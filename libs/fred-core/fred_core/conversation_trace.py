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

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

TraceIdentifier = Annotated[str, StringConstraints(min_length=1, max_length=255)]
CallIdentifier = Annotated[
    str, StringConstraints(min_length=1, max_length=255, pattern=r"^[a-zA-Z0-9_.:-]+$")
]
TraceId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
SpanId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{16}$")]
MAX_TRACE_CALL_IDS = 128


class TraceOutcome(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    UNKNOWN = "unknown"


class TraceAvailability(StrEnum):
    METADATA_ONLY = "metadata_only"
    PARTIAL = "partial"


class TraceAdmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: TraceIdentifier
    exchange_id: TraceIdentifier
    user_id: TraceIdentifier
    agent_instance_id: TraceIdentifier
    history_rank: Annotated[int, Field(ge=0, lt=2**31)]


class TraceAdmission(BaseModel):
    capture_id: TraceIdentifier


class TraceFinalization(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: TraceOutcome
    duration_ms: Annotated[int, Field(ge=0, le=2**31 - 1)]
    turn_number: Annotated[int, Field(ge=1, lt=2**31)] | None = None
    call_ids: Annotated[list[CallIdentifier], Field(max_length=MAX_TRACE_CALL_IDS)] = (
        Field(default_factory=list)
    )
    trace_id: TraceId | None = None
    span_id: SpanId | None = None
    discarded: bool = False
