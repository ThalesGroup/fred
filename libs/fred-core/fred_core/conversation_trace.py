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
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic.alias_generators import to_camel

from fred_core.history.history_schema import ChatMessage, TraceFailureCategory

TraceIdentifier = Annotated[str, StringConstraints(min_length=1, max_length=255)]
CallIdentifier = Annotated[
    str, StringConstraints(min_length=1, max_length=255, pattern=r"^[a-zA-Z0-9_.:-]+$")
]
TraceId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
SpanId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{16}$")]
TraceRank = Annotated[int, Field(ge=0, lt=2**31)]
MAX_TRACE_CALL_IDS = 128
MAX_TRACE_SPANS = 256
TRACE_DEFAULT_SAMPLING = 100
TRACE_DEFAULT_RETENTION_DAYS = 30
TRACE_DEFAULT_STORAGE_BYTES = 20_000_000_000
TRACE_BINDING_SESSION_HEADER = "X-Fred-Trace-Session"
TRACE_BINDING_WORKLOAD_HEADER = "X-Fred-Trace-Workload-Authorization"
TRACE_SEGMENT_HEADER = "X-Fred-Trace-Segment"
TRACE_RESUME_HEADER = "X-Fred-Trace-Resume"
TRACE_ADMISSION_STATUS_HEADER = "X-Fred-Trace-Admission-Status"


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

    def covers_exchange(self, first_rank: int, exchange_id: str) -> bool:
        # A legacy capture can store the rank where it first observed a resume.
        return exchange_id == self.exchange_id or (first_rank, exchange_id) < (
            self.first_rank,
            self.exchange_id,
        )

    @model_validator(mode="after")
    def _check_ranks(self) -> TraceHistoryBoundary:
        if self.last_rank < self.first_rank:
            raise ValueError("the saved history boundary is inverted")
        if self.started_at.tzinfo is None:
            self.started_at = self.started_at.replace(tzinfo=timezone.utc)
        return self


class TraceHistoryIncident(BaseModel):
    cutoff: TraceHistoryBoundary
    support_error_ref: TraceId
    failure_category: TraceFailureCategory | None = None


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


TRACE_OWNER_VISIBILITY_BATCH = 100


class TraceOwnerVisibilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: TraceIdentifier
    session_ids: Annotated[
        list[TraceIdentifier],
        Field(min_length=1, max_length=TRACE_OWNER_VISIBILITY_BATCH),
    ]


class TraceAdmission(BaseModel):
    capture_id: TraceIdentifier
    stream_offset_ms: TraceRank = 0
    segment_id: UUID | None = None
    streaming_blocks: bool = False


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
    tool_ref: EvidenceReference | None = None
    attempt: Annotated[int, Field(ge=1)]
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
    decoded: bool = False
    total_bytes: TraceRank | None = None
    offset: TraceRank | None = None
    next_offset: TraceRank | None = None


class TraceHttpEvidence(BaseModel):
    version: Literal[1] = 1
    method: str
    target: str
    bearer_replay: bool | None = None
    request_headers: dict[str, str]
    response_headers: dict[str, str]
    request_body: TraceHttpBody | None = None
    response_body: TraceHttpBody | None = None


TRACE_MAX_SSE_FRAMES = 512
TRACE_SSE_PAGE_FRAMES = 256
TRACE_MAX_SSE_SEGMENTS = 8
TRACE_SSE_SEGMENT_BYTES = 512 * 1024
TRACE_SSE_FRAME_BYTES = 64 * 1024
TRACE_HEADER_VALUE_BYTES = 256


class TraceSseKind(StrEnum):
    TEXT = "text"
    REASONING = "reasoning"
    TOOL = "tool"
    STATUS = "status"
    DONE = "done"
    ERROR = "error"
    OTHER = "other"


class TraceSseEnding(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CLOSED = "closed"
    TIMEOUT = "timeout"
    WATCHDOG_TIMEOUT = "watchdog_timeout"
    TRUNCATED = "truncated"
    TRANSPORT_ERROR = "transport_error"
    HTTP_REJECTED = "http_rejected"
    NOT_SSE = "not_sse"


class TraceSseAvailability(StrEnum):
    CAPTURED = "captured"
    EMPTY = "empty"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class TraceSseEvent(BaseModel):
    at_ms: TraceRank
    kind: TraceSseKind
    size: TraceRank
    offset: TraceRank | None = None


class TraceSseFramePage(BaseModel):
    start_index: TraceRank
    frames: Annotated[list[TraceSseEvent], Field(max_length=TRACE_SSE_PAGE_FRAMES)]
    raw_data: str | None = None


class TraceSseLane(BaseModel):
    ref: EvidenceReference
    started_ms: TraceRank
    headers_ms: TraceRank | None
    headers_available: bool = False
    end_ms: TraceRank
    last_event_ms: TraceRank | None
    longest_gap: tuple[TraceRank, TraceRank] | None
    availability: TraceSseAvailability
    ending: TraceSseEnding
    frame_count: TraceRank
    frames: Annotated[list[TraceSseEvent], Field(max_length=TRACE_MAX_SSE_FRAMES)]
    paged: bool = False
    page_starts_ms: list[TraceRank] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_frame_storage(self) -> TraceSseLane:
        if self.paged and self.frames:
            raise ValueError("paged SSE lanes cannot contain inline frames")
        if not self.paged and (
            self.page_starts_ms
            or any(
                frame.offset is not None
                and (
                    not 0 < frame.size <= TRACE_SSE_FRAME_BYTES
                    or frame.offset + frame.size > TRACE_SSE_SEGMENT_BYTES
                )
                for frame in self.frames
            )
        ):
            raise ValueError("invalid inline SSE metadata")
        return self

    @property
    def raw_size(self) -> int:
        """Return the fully indexed byte range, including retained partial streams."""
        end = 0
        for frame in self.frames:
            if frame.offset is None:
                continue
            if frame.offset != end:
                return 0
            end += frame.size
        return end


class TraceSseSegment(BaseModel):
    observed_through_rank: TraceRank | None
    outgoing: TraceSseLane | None
    provider: list[TraceSseLane]

    @property
    def lanes(self) -> list[TraceSseLane]:
        return [self.outgoing, *self.provider] if self.outgoing else self.provider

    @property
    def ref(self) -> str:
        return self.lanes[0].ref

    @model_validator(mode="after")
    def _check_frame_limit(self) -> TraceSseSegment:
        if not self.lanes:
            raise ValueError("SSE segment must contain a lane")
        if sum(len(lane.frames) for lane in self.lanes) > TRACE_MAX_SSE_FRAMES:
            raise ValueError("too many SSE timing markers in one execution segment")
        return self


class TraceSseHeaderAccess(BaseModel):
    grant_id: str | None = None
    local_content_access: bool = False


class TraceSseArtifactAccess(TraceSseHeaderAccess):
    offset: Annotated[int, Field(ge=0, le=TRACE_SSE_SEGMENT_BYTES)] | None = None
    size: Annotated[int, Field(gt=0, le=TRACE_SSE_SEGMENT_BYTES)] | None = None
    index: TraceRank | None = None


class TraceSseFrame(BaseModel):
    encoding: Literal["base64"] = "base64"
    data: str


class TraceSseHeaders(BaseModel):
    headers: Annotated[
        dict[str, Annotated[str, Field(max_length=TRACE_HEADER_VALUE_BYTES)]],
        Field(max_length=16),
    ]


TRACE_MAX_MODEL_CALLS = 64
TRACE_MAX_NORMALIZATION_REWRITES = 24
TraceToolFingerprint = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class TraceNormalizationStatus(StrEnum):
    SKIPPED = "skipped"
    UNCHANGED = "unchanged"
    CORRECTED = "corrected"
    UNAVAILABLE = "unavailable"


class TraceNormalizationRewrite(BaseModel):
    choice_index: int
    tool_index: int
    original_id: Literal["null"] = "null"
    replacement_id: None = None
    tool_call_id: CallIdentifier | None = None
    frame_index: TraceRank | None = None


class TraceNormalization(BaseModel):
    attempt_ref: EvidenceReference
    status: TraceNormalizationStatus
    rewrites: Annotated[
        list[TraceNormalizationRewrite],
        Field(max_length=TRACE_MAX_NORMALIZATION_REWRITES),
    ]
    partial: bool = False


class TraceModelCall(BaseModel):
    ref: EvidenceReference
    call_id: CallIdentifier
    model: CallIdentifier | None
    observed_through_rank: TraceRank | None
    completeness: TraceHttpCompleteness


class TraceModelIndex(TraceModelCall):
    related_tools: Annotated[list[TraceToolFingerprint], Field(max_length=32)] = Field(
        default_factory=list
    )
    observed_invalid_tools: Annotated[
        list[TraceToolFingerprint], Field(max_length=32)
    ] = Field(default_factory=list)


class TraceModelArtifactAccess(BaseModel):
    grant_id: str | None = None
    local_content_access: bool = False
    owner_id: TraceIdentifier
    observed_through_rank: TraceRank | None


class TraceModelOutputState(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    ABSENT = "absent"
    UNAVAILABLE = "unavailable"


class TraceModelSnapshot(BaseModel):
    messages: list[dict[str, object]]
    tools: list[dict[str, object]] = Field(default_factory=list)
    partial: bool = False


class TraceModelOrigin(BaseModel):
    exchange_id: TraceIdentifier
    history_rank: TraceRank
    turn_number: int | None
    call_id: CallIdentifier


class TraceModelEvidence(BaseModel):
    version: Literal[1] = 1
    input: TraceModelSnapshot | None
    output: TraceModelSnapshot | None
    output_state: TraceModelOutputState
    normalization: Annotated[
        list[TraceNormalization], Field(max_length=TRACE_MAX_HTTP_ATTEMPTS)
    ] = Field(default_factory=list)
    matched_results: list[dict[str, object]] = Field(default_factory=list)
    origins: list[TraceModelOrigin] = Field(default_factory=list)


TRACE_MAX_TOOL_CALLS = 64


class TraceToolSource(StrEnum):
    NATIVE = "native"
    MCP = "mcp"
    KNOWLEDGE_FLOW = "knowledge_flow"


class TraceToolOutcome(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class TraceToolModelLink(BaseModel):
    call_id: CallIdentifier
    relation: Literal["requested", "received"]


class TraceToolCall(BaseModel):
    ref: EvidenceReference
    call_id: CallIdentifier | None
    tool_name: CallIdentifier | None
    source: TraceToolSource
    outcome: TraceToolOutcome
    attempt: Annotated[int, Field(ge=1)]
    duration_ms: TraceRank
    observed_through_rank: TraceRank | None
    completeness: TraceHttpCompleteness
    model_calls: Annotated[
        list[TraceToolModelLink], Field(max_length=2 * TRACE_MAX_MODEL_CALLS)
    ] = Field(default_factory=list)
    http_attempts: list[TraceHttpAttempt] = Field(default_factory=list)


class TraceToolArtifactAccess(BaseModel):
    grant_id: str | None = None
    local_content_access: bool = False
    observed_through_rank: TraceRank | None


class TraceToolEvidence(BaseModel):
    version: Literal[1] = 1
    input: object = None
    output: object = None
    model_result: dict[str, object] | None = None
    partial: bool = False


TraceStorageBytes = Annotated[int, Field(ge=0, le=16 * 1024 * 1024)]
TraceStorageRefs = dict[EvidenceReference, TraceStorageBytes]


class TraceDegradation(StrEnum):
    CAPACITY = "capacity"
    QUEUE = "queue"
    STORAGE = "storage"


class TraceStorageReservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publication_id: UUID
    objects: TraceStorageRefs
    segment_id: UUID | None = None
    incremental: bool = False


class TraceStorageReservationState(StrEnum):
    RESERVED = "reserved"
    CAPACITY = "capacity"
    UNAVAILABLE = "unavailable"
    FENCED = "fenced"


class TraceStoragePublication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publication_id: UUID
    stored: TraceStorageRefs
    uncertain: list[EvidenceReference]


class TraceStorageCleanup(BaseModel):
    id: UUID
    lease: UUID
    session_id: TraceIdentifier
    refs: list[EvidenceReference]
    measure: bool = False


class TraceStorageCleanupResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lease: UUID
    success: bool = True
    measured: TraceStorageRefs | None = None


class TraceCheckpointStatus(StrEnum):
    PERSISTED = "persisted"
    NOT_OBSERVED = "not_observed"
    UNCONFIGURED = "unconfigured"
    UNKNOWN = "unknown"


class TraceFinalizationFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: TraceOutcome
    failure_category: TraceFailureCategory | None = None
    support_error_ref: TraceId | None = None
    duration_ms: Annotated[int, Field(ge=0, le=2**31 - 1)]
    turn_number: Annotated[int, Field(ge=1, lt=2**31)] | None = None
    call_ids: list[CallIdentifier] = Field(default_factory=list)
    trace_id: TraceId | None = None
    span_id: SpanId | None = None
    checkpoint_status: TraceCheckpointStatus = TraceCheckpointStatus.UNKNOWN
    discarded: bool = False


class OtlpTraceStringValue(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )

    string_value: CallIdentifier


class OtlpTraceAttribute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: Literal[
        "fred.call.id",
        "fred.evidence.ref",
        "fred.capture.ref",
        "fred.session.id",
        "fred.exchange.id",
    ]
    value: OtlpTraceStringValue


class OtlpTraceSpan(BaseModel):
    """The bounded, content-free subset of the OTLP/JSON Span message."""

    model_config = ConfigDict(
        extra="forbid",
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )

    trace_id: TraceId
    span_id: SpanId
    parent_span_id: SpanId | Literal[""] = ""
    name: CallIdentifier
    start_time_unix_nano: Annotated[str, StringConstraints(pattern=r"^[0-9]{1,20}$")]
    end_time_unix_nano: Annotated[str, StringConstraints(pattern=r"^[0-9]{1,20}$")]
    attributes: Annotated[list[OtlpTraceAttribute], Field(max_length=5)] = Field(
        default_factory=list
    )


class TraceAdmissionReconciliation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    admission: TraceAdmissionRequest
    facts: TraceFinalizationFacts


class TraceFinalization(TraceFinalizationFacts):
    segment_id: UUID | None = None
    evidence_pending: bool = False
    recording_complete: bool | None = None
    http_attempts: list[TraceHttpAttempt] = Field(default_factory=list)
    http_incomplete: bool = False
    degradation: TraceDegradation | None = None
    storage: TraceStoragePublication | None = None
    sse: TraceSseSegment | None = None
    model_calls: list[TraceModelIndex] = Field(default_factory=list)
    tool_calls: list[TraceToolCall] = Field(default_factory=list)
    otel_spans: list[OtlpTraceSpan] = Field(default_factory=list)
