// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
//! Wire models shared with the trace recorder and inspector.
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use utoipa::ToSchema;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, PartialEq, Eq)]
pub enum TraceOutcome {
    #[serde(rename = "completed")]
    Completed,
    #[serde(rename = "failed")]
    Failed,
    #[serde(rename = "paused")]
    Paused,
    #[serde(rename = "unknown")]
    Unknown,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, PartialEq, Eq)]
pub enum TraceAvailability {
    #[serde(rename = "metadata_only")]
    MetadataOnly,
    #[serde(rename = "captured")]
    Captured,
    #[serde(rename = "partial")]
    Partial,
    #[serde(rename = "history_only")]
    HistoryOnly,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceHistoryBoundary {
    pub exchange_id: String,
    pub first_rank: i64,
    pub last_rank: i64,
    pub turn_number: i64,
    pub started_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceHistoryIncident {
    pub cutoff: TraceHistoryBoundary,
    pub support_error_ref: String,
    pub failure_category: Option<TraceFailureCategory>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceHistoryAccess {
    pub owner_id: String,
    pub cutoff: Option<TraceHistoryBoundary>,
    pub grant_id: Option<String>,
    #[serde(default)]
    pub local_content_access: bool,
    pub captured_rank: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceHistoryTranscript {
    pub available: bool,
    pub messages: Vec<TraceHistoryMessage>,
    pub next_rank: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceAdmissionRequest {
    pub session_id: String,
    pub exchange_id: String,
    pub user_id: String,
    pub agent_instance_id: String,
    pub history_rank: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceOwnerVisibilityRequest {
    pub user_id: String,
    pub session_ids: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceAdmission {
    pub capture_id: String,
    #[serde(default)]
    pub stream_offset_ms: i64,
    pub segment_id: Option<Uuid>,
    #[serde(default)]
    pub streaming_blocks: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, PartialEq, Eq)]
pub enum TraceHttpCompleteness {
    #[serde(rename = "complete")]
    Complete,
    #[serde(rename = "partial")]
    Partial,
    #[serde(rename = "unavailable")]
    Unavailable,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, PartialEq, Eq)]
pub enum TraceHttpFailureStage {
    #[serde(rename = "response_headers")]
    ResponseHeaders,
    #[serde(rename = "response_body")]
    ResponseBody,
    #[serde(rename = "http_status")]
    HttpStatus,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceHttpAttempt {
    pub r#ref: String,
    pub call_id: String,
    pub tool_ref: Option<String>,
    pub attempt: i64,
    pub model: Option<String>,
    pub release: Option<String>,
    pub status: Option<i64>,
    pub upstream_id: Option<String>,
    pub failure_stage: Option<TraceHttpFailureStage>,
    pub duration_ms: i64,
    pub request_bytes: i64,
    pub response_bytes: i64,
    pub observed_through_rank: Option<i64>,
    pub completeness: TraceHttpCompleteness,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceHttpArtifactAccess {
    pub grant_id: Option<String>,
    #[serde(default)]
    pub local_content_access: bool,
    pub attempt: TraceHttpAttempt,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceHttpBody {
    pub encoding: String,
    pub data: String,
    pub complete: bool,
    #[serde(default)]
    pub decoded: bool,
    pub total_bytes: Option<i64>,
    pub offset: Option<i64>,
    pub next_offset: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceHttpEvidence {
    pub version: i64,
    pub method: String,
    pub target: String,
    pub bearer_replay: Option<bool>,
    pub request_headers: std::collections::BTreeMap<String, String>,
    pub response_headers: std::collections::BTreeMap<String, String>,
    pub request_body: Option<TraceHttpBody>,
    pub response_body: Option<TraceHttpBody>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, PartialEq, Eq)]
pub enum TraceSseKind {
    #[serde(rename = "text")]
    Text,
    #[serde(rename = "reasoning")]
    Reasoning,
    #[serde(rename = "tool")]
    Tool,
    #[serde(rename = "status")]
    Status,
    #[serde(rename = "done")]
    Done,
    #[serde(rename = "error")]
    Error,
    #[serde(rename = "other")]
    Other,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, PartialEq, Eq)]
pub enum TraceSseEnding {
    #[serde(rename = "completed")]
    Completed,
    #[serde(rename = "failed")]
    Failed,
    #[serde(rename = "paused")]
    Paused,
    #[serde(rename = "closed")]
    Closed,
    #[serde(rename = "timeout")]
    Timeout,
    #[serde(rename = "watchdog_timeout")]
    WatchdogTimeout,
    #[serde(rename = "truncated")]
    Truncated,
    #[serde(rename = "transport_error")]
    TransportError,
    #[serde(rename = "http_rejected")]
    HttpRejected,
    #[serde(rename = "not_sse")]
    NotSse,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, PartialEq, Eq)]
pub enum TraceSseAvailability {
    #[serde(rename = "captured")]
    Captured,
    #[serde(rename = "empty")]
    Empty,
    #[serde(rename = "partial")]
    Partial,
    #[serde(rename = "unavailable")]
    Unavailable,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceSseEvent {
    pub at_ms: i64,
    pub kind: TraceSseKind,
    pub size: i64,
    pub offset: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceSseFramePage {
    pub start_index: i64,
    pub frames: Vec<TraceSseEvent>,
    pub raw_data: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceSseLane {
    pub r#ref: String,
    pub started_ms: i64,
    pub headers_ms: Option<i64>,
    #[serde(default)]
    pub headers_available: bool,
    pub end_ms: i64,
    pub last_event_ms: Option<i64>,
    pub longest_gap: Option<[i64; 2]>,
    pub availability: TraceSseAvailability,
    pub ending: TraceSseEnding,
    pub frame_count: i64,
    #[serde(default)]
    pub page_starts_ms: Vec<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceSseSegment {
    pub observed_through_rank: Option<i64>,
    pub outgoing: Option<TraceSseLane>,
    pub provider: Vec<TraceSseLane>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceSseHeaderAccess {
    pub grant_id: Option<String>,
    #[serde(default)]
    pub local_content_access: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceSseArtifactAccess {
    pub grant_id: Option<String>,
    #[serde(default)]
    pub local_content_access: bool,
    pub index: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceSseFrame {
    pub encoding: String,
    pub data: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceSseHeaders {
    pub headers: std::collections::BTreeMap<String, String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, PartialEq, Eq)]
pub enum TraceNormalizationStatus {
    #[serde(rename = "skipped")]
    Skipped,
    #[serde(rename = "unchanged")]
    Unchanged,
    #[serde(rename = "corrected")]
    Corrected,
    #[serde(rename = "unavailable")]
    Unavailable,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceNormalizationRewrite {
    pub choice_index: i64,
    pub tool_index: i64,
    pub original_id: String,
    #[serde(default)]
    pub replacement_id: Value,
    pub tool_call_id: Option<String>,
    pub frame_index: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceNormalization {
    pub attempt_ref: String,
    pub status: TraceNormalizationStatus,
    pub rewrites: Vec<TraceNormalizationRewrite>,
    #[serde(default)]
    pub partial: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceModelCall {
    pub r#ref: String,
    pub call_id: String,
    pub model: Option<String>,
    pub observed_through_rank: Option<i64>,
    pub completeness: TraceHttpCompleteness,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceModelIndex {
    pub r#ref: String,
    pub call_id: String,
    pub model: Option<String>,
    pub observed_through_rank: Option<i64>,
    pub completeness: TraceHttpCompleteness,
    #[serde(default)]
    pub related_tools: Vec<String>,
    #[serde(default)]
    pub observed_invalid_tools: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceModelArtifactAccess {
    pub grant_id: Option<String>,
    #[serde(default)]
    pub local_content_access: bool,
    pub owner_id: String,
    pub observed_through_rank: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, PartialEq, Eq)]
pub enum TraceModelOutputState {
    #[serde(rename = "complete")]
    Complete,
    #[serde(rename = "partial")]
    Partial,
    #[serde(rename = "absent")]
    Absent,
    #[serde(rename = "unavailable")]
    Unavailable,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceModelSnapshot {
    pub messages: Vec<std::collections::BTreeMap<String, Value>>,
    #[serde(default)]
    pub tools: Vec<std::collections::BTreeMap<String, Value>>,
    #[serde(default)]
    pub partial: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceModelOrigin {
    pub exchange_id: String,
    pub history_rank: i64,
    pub turn_number: Option<i64>,
    pub call_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceModelEvidence {
    pub version: i64,
    pub input: Option<TraceModelSnapshot>,
    pub output: Option<TraceModelSnapshot>,
    pub output_state: TraceModelOutputState,
    #[serde(default)]
    pub normalization: Vec<TraceNormalization>,
    #[serde(default)]
    pub matched_results: Vec<std::collections::BTreeMap<String, Value>>,
    #[serde(default)]
    pub origins: Vec<TraceModelOrigin>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, PartialEq, Eq)]
pub enum TraceToolSource {
    #[serde(rename = "native")]
    Native,
    #[serde(rename = "mcp")]
    Mcp,
    #[serde(rename = "knowledge_flow")]
    KnowledgeFlow,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, PartialEq, Eq)]
pub enum TraceToolOutcome {
    #[serde(rename = "success")]
    Success,
    #[serde(rename = "error")]
    Error,
    #[serde(rename = "paused")]
    Paused,
    #[serde(rename = "cancelled")]
    Cancelled,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceToolModelLink {
    pub call_id: String,
    pub relation: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceToolCall {
    pub r#ref: String,
    pub call_id: Option<String>,
    pub tool_name: Option<String>,
    pub source: TraceToolSource,
    pub outcome: TraceToolOutcome,
    pub attempt: i64,
    pub duration_ms: i64,
    pub observed_through_rank: Option<i64>,
    pub completeness: TraceHttpCompleteness,
    #[serde(default)]
    pub model_calls: Vec<TraceToolModelLink>,
    #[serde(default)]
    pub http_attempts: Vec<TraceHttpAttempt>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceToolArtifactAccess {
    pub grant_id: Option<String>,
    #[serde(default)]
    pub local_content_access: bool,
    pub observed_through_rank: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceToolEvidence {
    pub version: i64,
    #[serde(default)]
    pub input: Value,
    #[serde(default)]
    pub output: Value,
    pub model_result: Option<std::collections::BTreeMap<String, Value>>,
    #[serde(default)]
    pub partial: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, PartialEq, Eq)]
pub enum TraceDegradation {
    #[serde(rename = "capacity")]
    Capacity,
    #[serde(rename = "queue")]
    Queue,
    #[serde(rename = "storage")]
    Storage,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceStorageReservation {
    pub publication_id: Uuid,
    pub objects: std::collections::BTreeMap<String, i64>,
    pub segment_id: Option<Uuid>,
    #[serde(default)]
    pub incremental: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, PartialEq, Eq)]
pub enum TraceStorageReservationState {
    #[serde(rename = "reserved")]
    Reserved,
    #[serde(rename = "capacity")]
    Capacity,
    #[serde(rename = "unavailable")]
    Unavailable,
    #[serde(rename = "fenced")]
    Fenced,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceStoragePublication {
    pub publication_id: Uuid,
    pub stored: std::collections::BTreeMap<String, i64>,
    pub uncertain: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceStorageCleanup {
    pub id: Uuid,
    pub lease: Uuid,
    pub session_id: String,
    pub refs: Vec<String>,
    #[serde(default)]
    pub measure: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceStorageCleanupResult {
    pub lease: Uuid,
    #[serde(default)]
    pub success: bool,
    pub measured: Option<std::collections::BTreeMap<String, i64>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, PartialEq, Eq)]
pub enum TraceCheckpointStatus {
    #[serde(rename = "persisted")]
    Persisted,
    #[serde(rename = "not_observed")]
    NotObserved,
    #[serde(rename = "unconfigured")]
    Unconfigured,
    #[serde(rename = "unknown")]
    Unknown,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceFinalizationFacts {
    pub outcome: TraceOutcome,
    pub failure_category: Option<TraceFailureCategory>,
    pub support_error_ref: Option<String>,
    pub duration_ms: i64,
    pub turn_number: Option<i64>,
    #[serde(default)]
    pub call_ids: Vec<String>,
    pub trace_id: Option<String>,
    pub span_id: Option<String>,
    pub checkpoint_status: TraceCheckpointStatus,
    #[serde(default)]
    pub discarded: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct OtlpTraceStringValue {
    pub string_value: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct OtlpTraceAttribute {
    pub key: String,
    pub value: OtlpTraceStringValue,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "camelCase")]
pub struct OtlpTraceSpan {
    pub trace_id: String,
    pub span_id: String,
    pub parent_span_id: String,
    pub name: String,
    pub start_time_unix_nano: String,
    pub end_time_unix_nano: String,
    #[serde(default)]
    pub attributes: Vec<OtlpTraceAttribute>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceAdmissionReconciliation {
    pub admission: TraceAdmissionRequest,
    pub facts: TraceFinalizationFacts,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceFinalization {
    pub outcome: TraceOutcome,
    pub failure_category: Option<TraceFailureCategory>,
    pub support_error_ref: Option<String>,
    pub duration_ms: i64,
    pub turn_number: Option<i64>,
    #[serde(default)]
    pub call_ids: Vec<String>,
    pub trace_id: Option<String>,
    pub span_id: Option<String>,
    pub checkpoint_status: TraceCheckpointStatus,
    #[serde(default)]
    pub discarded: bool,
    pub segment_id: Option<Uuid>,
    #[serde(default)]
    pub evidence_pending: bool,
    pub recording_complete: Option<bool>,
    #[serde(default)]
    pub http_attempts: Vec<TraceHttpAttempt>,
    #[serde(default)]
    pub http_incomplete: bool,
    pub degradation: Option<TraceDegradation>,
    pub storage: Option<TraceStoragePublication>,
    pub sse: Option<TraceSseSegment>,
    #[serde(default)]
    pub model_calls: Vec<TraceModelIndex>,
    #[serde(default)]
    pub tool_calls: Vec<TraceToolCall>,
    #[serde(default)]
    pub otel_spans: Vec<OtlpTraceSpan>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct ConversationTraceSettingsUpdate {
    pub enabled: Option<bool>,
    pub sampling_percent: Option<i64>,
    pub retention_days: Option<i64>,
    pub storage_cap_bytes: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct ConversationTraceSettings {
    pub enabled: bool,
    pub sampling_percent: i64,
    pub retention_days: i64,
    pub storage_cap_bytes: i64,
    pub used_bytes: i64,
    pub reserved_bytes: i64,
    pub degraded: bool,
    pub degradation_reason: Option<TraceDegradation>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct DeleteConversationTracesRequest {
    pub session_ids: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct DeleteConversationTracesResult {
    pub removed: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, PartialEq, Eq)]
pub enum TraceExportMode {
    #[serde(rename = "metadata_only")]
    MetadataOnly,
    #[serde(rename = "shared_content")]
    SharedContent,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct ExportConversationTracesRequest {
    pub session_ids: Vec<String>,
    pub mode: TraceExportMode,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceConsentRequest {
    pub exchange_id: String,
    pub last_rank: i64,
    pub expected_version: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceConsentGrant {
    pub grant_id: String,
    pub cutoff: TraceHistoryBoundary,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceConsentState {
    pub consent: Option<TraceConsentGrant>,
    pub consent_version: Option<String>,
    pub available_cutoff: Option<TraceHistoryBoundary>,
    #[serde(default)]
    pub history_unavailable: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceIncidentOffer {
    pub cutoff: TraceHistoryBoundary,
    pub consent_version: Option<String>,
    pub consent_cutoff: Option<TraceHistoryBoundary>,
    pub capture_available: bool,
    pub reported: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, PartialEq, Eq)]
pub enum TraceContentAccess {
    #[serde(rename = "masked")]
    Masked,
    #[serde(rename = "shared")]
    Shared,
    #[serde(rename = "local")]
    Local,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, PartialEq, Eq)]
pub enum TraceConsentFilter {
    #[serde(rename = "all")]
    All,
    #[serde(rename = "shared")]
    Shared,
    #[serde(rename = "masked")]
    Masked,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, PartialEq, Eq)]
pub enum TraceCatalogSort {
    #[serde(rename = "latest")]
    Latest,
    #[serde(rename = "title")]
    Title,
    #[serde(rename = "user")]
    User,
    #[serde(rename = "team")]
    Team,
    #[serde(rename = "outcome")]
    Outcome,
    #[serde(rename = "consent")]
    Consent,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceTeamOption {
    pub team_id: String,
    pub name: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct ConversationTraceSummary {
    pub session_id: String,
    pub agent_display_name: String,
    pub title: Option<String>,
    pub user_id: Option<String>,
    pub username: Option<String>,
    pub user_display_name: Option<String>,
    pub team_id: String,
    pub team_name: String,
    pub access: TraceContentAccess,
    pub latest_started_at: DateTime<Utc>,
    pub outcome: TraceOutcome,
    pub failure_category: Option<TraceFailureCategory>,
    pub availability: TraceAvailability,
    pub support_error_ref: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct ConversationTraceCatalog {
    pub conversations: Vec<ConversationTraceSummary>,
    pub next_cursor: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceReportedFailure {
    pub support_error_ref: String,
    pub failure_category: Option<TraceFailureCategory>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct ConversationTraceTurn {
    pub exchange_id: String,
    pub turn_number: Option<i64>,
    pub started_at: DateTime<Utc>,
    pub duration_ms: Option<i64>,
    pub outcome: TraceOutcome,
    pub checkpoint_status: TraceCheckpointStatus,
    pub failure_category: Option<TraceFailureCategory>,
    pub availability: TraceAvailability,
    pub capture_status: Option<String>,
    pub degradation_reason: Option<TraceDegradation>,
    pub call_ids: Vec<String>,
    pub trace_id: Option<String>,
    pub span_id: Option<String>,
    pub access: TraceContentAccess,
    pub retained_cutoff: Option<TraceHistoryBoundary>,
    pub support_error_ref: Option<String>,
    #[serde(default)]
    pub reported_failures: Vec<TraceReportedFailure>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct ConversationTraceDetail {
    pub session_id: String,
    pub title: Option<String>,
    pub agent_display_name: String,
    pub team_id: String,
    pub turns: Vec<ConversationTraceTurn>,
    pub next_cursor: Option<String>,
    pub consent_cutoff: Option<TraceHistoryBoundary>,
    pub consent_version: Option<String>,
    #[serde(default)]
    pub can_renew_title_consent: bool,
    #[serde(default)]
    pub local_content_access: bool,
    #[serde(default)]
    pub retained_after_delete: bool,
}

/// The inspector preserves the runtime history contract, including extension parts.
#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceHistoryMessage {
    pub session_id: String,
    pub exchange_id: String,
    pub rank: i64,
    pub timestamp: DateTime<Utc>,
    pub role: String,
    pub channel: String,
    pub parts: Vec<TraceHistoryPart>,
    pub metadata: Value,
}
#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct TraceHistoryPart {
    #[serde(rename = "type")]
    pub kind: String,
    pub text: Option<String>,
    #[serde(flatten)]
    pub fields: std::collections::BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TraceFailureCategory {
    #[serde(rename = "http_5xx")]
    Http5xx,
    #[serde(rename = "http_429")]
    Http429,
    #[serde(rename = "http_400")]
    Http400,
    #[serde(rename = "http_other_4xx")]
    HttpOther4xx,
    StreamInterrupted,
    TimeoutOrConnection,
    ContextLimit,
    ToolOrCapability,
    InternalOrUnknown,
}
