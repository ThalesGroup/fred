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
from enum import StrEnum
from typing import Annotated, Literal

from fred_core.conversation_trace import (
    TraceAvailability,
    TraceCheckpointStatus,
    TraceDegradation,
    TraceHistoryBoundary,
    TraceId,
    TraceIdentifier,
    TraceOutcome,
    TraceRank,
)
from fred_core.history.history_schema import TraceFailureCategory
from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class ConversationTraceSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    sampling_percent: Annotated[int, Field(ge=0, le=100)] | None = None
    retention_days: Annotated[int, Field(ge=1, le=3650)] | None = None
    storage_cap_bytes: Annotated[int, Field(ge=1, le=10_000_000_000_000)] | None = None


class ConversationTraceSettings(BaseModel):
    enabled: bool
    sampling_percent: int
    retention_days: int
    storage_cap_bytes: int
    used_bytes: int
    reserved_bytes: int
    degraded: bool
    degradation_reason: TraceDegradation | None


class DeleteConversationTracesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_ids: Annotated[list[TraceIdentifier], Field(min_length=1, max_length=100)]


class DeleteConversationTracesResult(BaseModel):
    removed: int


class TraceExportMode(StrEnum):
    METADATA_ONLY = "metadata_only"
    SHARED_CONTENT = "shared_content"


class ExportConversationTracesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_ids: Annotated[list[TraceIdentifier], Field(min_length=1, max_length=100)]
    mode: TraceExportMode


class TraceConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exchange_id: TraceIdentifier
    last_rank: TraceRank
    expected_version: str | None


class ManualTraceConsentRequest(TraceConsentRequest):
    source_note: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]


class TraceConsentGrant(BaseModel):
    grant_id: str
    cutoff: TraceHistoryBoundary


class TraceConsentState(BaseModel):
    consent: TraceConsentGrant | None = None
    consent_version: str | None = None
    available_cutoff: TraceHistoryBoundary | None = None
    history_unavailable: bool = False


class TraceIncidentOffer(BaseModel):
    cutoff: TraceHistoryBoundary
    consent_version: str | None
    consent_cutoff: TraceHistoryBoundary | None
    capture_available: bool
    reported: bool


class TraceContentAccess(StrEnum):
    MASKED = "masked"
    SHARED = "shared"
    LOCAL = "local"


class TraceConsentFilter(StrEnum):
    ALL = "all"
    SHARED = "shared"
    MASKED = "masked"


class TraceCatalogSort(StrEnum):
    LATEST = "latest"
    TITLE = "title"
    USER = "user"
    TEAM = "team"
    OUTCOME = "outcome"
    CONSENT = "consent"


TraceOutcomeFilter = TraceOutcome | TraceFailureCategory


class TraceCatalogFilters(BaseModel):
    failed_only: bool = True
    outcomes: list[TraceOutcomeFilter] = Field(default_factory=list, max_length=20)
    team_ids: list[TraceIdentifier] = Field(default_factory=list, max_length=500)
    user_id: TraceIdentifier | None = None
    consent: TraceConsentFilter = TraceConsentFilter.ALL
    query: Annotated[str, Field(max_length=255)] = ""
    query_outcomes: list[TraceOutcomeFilter] = Field(
        default_factory=list, max_length=20
    )
    since: datetime | None = None
    until: datetime | None = None
    sort: TraceCatalogSort = TraceCatalogSort.LATEST
    direction: Literal["asc", "desc"] = "desc"
    limit: Annotated[int, Field(ge=1, le=100)] = 50
    cursor: Annotated[str, Field(max_length=291)] | None = None


class TraceTeamOption(BaseModel):
    team_id: str
    name: str


class ConversationTraceSummary(BaseModel):
    session_id: str
    agent_display_name: str
    title: str | None = None
    user_id: str | None = None
    username: str | None = None
    user_display_name: str | None = None
    team_id: str
    team_name: str
    access: TraceContentAccess
    latest_started_at: datetime
    outcome: TraceOutcome
    failure_category: TraceFailureCategory | None = None
    availability: TraceAvailability
    support_error_ref: TraceId | None = None


class ConversationTraceCatalog(BaseModel):
    conversations: list[ConversationTraceSummary]
    next_cursor: str | None


class TraceReportedFailure(BaseModel):
    support_error_ref: TraceId
    failure_category: TraceFailureCategory | None = None


TraceCaptureStatus = Literal["saving", "complete", "partial"]


class ConversationTraceTurn(BaseModel):
    exchange_id: str
    turn_number: int | None
    started_at: datetime
    duration_ms: int | None
    outcome: TraceOutcome
    checkpoint_status: TraceCheckpointStatus = TraceCheckpointStatus.UNKNOWN
    failure_category: TraceFailureCategory | None = None
    availability: TraceAvailability
    capture_status: TraceCaptureStatus | None = None
    degradation_reason: TraceDegradation | None = None
    call_ids: list[str]
    trace_id: str | None
    span_id: str | None
    access: TraceContentAccess = TraceContentAccess.MASKED
    retained_cutoff: TraceHistoryBoundary | None = None
    support_error_ref: TraceId | None = None
    reported_failures: list[TraceReportedFailure] = Field(default_factory=list)


class ConversationTraceDetail(BaseModel):
    session_id: str
    title: str | None = None
    agent_display_name: str
    team_id: str
    turns: list[ConversationTraceTurn]
    next_cursor: str | None
    consent_cutoff: TraceHistoryBoundary | None = None
    consent_version: str | None = None
    can_renew_title_consent: bool = False
    local_content_access: bool = False
    retained_after_delete: bool = False
