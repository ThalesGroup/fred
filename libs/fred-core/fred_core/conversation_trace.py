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

from datetime import datetime, timezone
from enum import StrEnum
from ipaddress import ip_address
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from fred_core.history.history_schema import ChatMessage

TraceIdentifier = Annotated[str, StringConstraints(min_length=1, max_length=255)]
CallIdentifier = Annotated[
    str, StringConstraints(min_length=1, max_length=255, pattern=r"^[a-zA-Z0-9_.:-]+$")
]
TraceId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
SpanId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{16}$")]
TraceRank = Annotated[int, Field(ge=0, lt=2**31)]
MAX_TRACE_CALL_IDS = 128


class TraceOutcome(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    UNKNOWN = "unknown"


class TraceAvailability(StrEnum):
    METADATA_ONLY = "metadata_only"
    CAPTURED = "captured"
    PARTIAL = "partial"
    HISTORY_ONLY = "history_only"


class TraceHistoryBoundary(BaseModel):
    exchange_id: TraceIdentifier
    first_rank: TraceRank
    last_rank: TraceRank
    turn_number: Annotated[int, Field(ge=1)]
    started_at: datetime

    @model_validator(mode="after")
    def _check_ranks(self) -> TraceHistoryBoundary:
        if self.last_rank < self.first_rank:
            raise ValueError("the saved history boundary is inverted")
        if self.started_at.tzinfo is None:
            self.started_at = self.started_at.replace(tzinfo=timezone.utc)
        return self


def is_local_trace_request(peer: str | None, host: str | None) -> bool:
    if peer is None or host is None:
        return False
    try:
        return ip_address(peer).is_loopback and (
            host == "localhost" or ip_address(host).is_loopback
        )
    except ValueError:
        return False


class TraceHistoryAccess(BaseModel):
    owner_id: TraceIdentifier
    cutoff: TraceHistoryBoundary | None = None
    grant_id: str | None = None
    local_content_access: bool = False
    captured_rank: TraceRank | None = None


class TraceHistoryTranscript(BaseModel):
    available: bool
    messages: list[ChatMessage]
    next_rank: TraceRank | None = None


class TraceAdmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: TraceIdentifier
    exchange_id: TraceIdentifier
    user_id: TraceIdentifier
    agent_instance_id: TraceIdentifier
    history_rank: TraceRank


class TraceAdmission(BaseModel):
    capture_id: TraceIdentifier


TRACE_MAX_HTTP_ATTEMPTS = 64
TRACE_HTTP_TURN_BYTES = 2 * 1024 * 1024
TRACE_HTTP_CHUNK_BYTES = 256 * 1024
EvidenceReference = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]


class TraceHttpCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class TraceHttpFailureStage(StrEnum):
    RESPONSE_HEADERS = "response_headers"
    RESPONSE_BODY = "response_body"
    HTTP_STATUS = "http_status"


class TraceHttpAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: EvidenceReference
    call_id: CallIdentifier
    attempt: Annotated[int, Field(ge=1, le=TRACE_MAX_HTTP_ATTEMPTS)]
    model: CallIdentifier | None = None
    release: CallIdentifier | None = None
    status: Annotated[int, Field(ge=100, le=599)] | None = None
    upstream_id: CallIdentifier | None = None
    failure_stage: TraceHttpFailureStage | None = None
    duration_ms: TraceRank
    request_bytes: TraceRank
    response_bytes: TraceRank
    observed_through_rank: TraceRank | None = None
    completeness: TraceHttpCompleteness


class TraceHttpArtifactAccess(BaseModel):
    grant_id: str | None = None
    local_content_access: bool = False
    attempt: TraceHttpAttempt


class TraceHttpBody(BaseModel):
    encoding: Literal["base64"] = "base64"
    data: str
    complete: bool


class TraceHttpEvidence(BaseModel):
    version: Literal[1] = 1
    method: str
    target: str
    request_headers: dict[str, str]
    response_headers: dict[str, str]
    request_body: TraceHttpBody | None = None
    response_body: TraceHttpBody | None = None


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
    http_attempts: Annotated[
        list[TraceHttpAttempt], Field(max_length=TRACE_MAX_HTTP_ATTEMPTS)
    ] = Field(default_factory=list)
    http_incomplete: bool = False
