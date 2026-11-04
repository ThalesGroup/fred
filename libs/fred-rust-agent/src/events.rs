// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! The events the browser receives.

use serde::Serialize;

use crate::search::SearchHit;

// Wire subset of fred-sdk/contracts/runtime.py::RuntimeEvent.
#[derive(Serialize, utoipa::ToSchema)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum RuntimeEvent {
    ThoughtStart {
        sequence: u64,
        thought_id: String,
        phase: &'static str,
        source: &'static str,
    },
    ThoughtDelta {
        sequence: u64,
        thought_id: String,
        delta: String,
    },
    ThoughtEnd {
        sequence: u64,
        thought_id: String,
    },
    ToolCall {
        sequence: u64,
        tool_name: &'static str,
        call_id: String,
        arguments: serde_json::Map<String, serde_json::Value>,
    },
    ToolResult {
        sequence: u64,
        tool_name: &'static str,
        call_id: String,
        content: String,
        is_error: bool,
        latency_ms: u64,
    },
    Status {
        sequence: u64,
        status: &'static str,
    },
    AssistantDelta {
        sequence: u64,
        delta: String,
    },
    #[serde(rename = "execution_error")]
    Error {
        sequence: u64,
        message: &'static str,
    },
    SessionTitle {
        sequence: u64,
        session_id: String,
    },
    Final {
        sequence: u64,
        content: String,
        sources: Vec<SearchHit>,
        finish_reason: &'static str,
    },
}

impl RuntimeEvent {
    /// The host may insert title events; sequence the final wire stream once.
    pub fn with_sequence(mut self, value: u64) -> Self {
        let (Self::Status { sequence, .. }
        | Self::AssistantDelta { sequence, .. }
        | Self::Final { sequence, .. }
        | Self::Error { sequence, .. }
        | Self::SessionTitle { sequence, .. }
        | Self::ThoughtStart { sequence, .. }
        | Self::ThoughtDelta { sequence, .. }
        | Self::ThoughtEnd { sequence, .. }
        | Self::ToolCall { sequence, .. }
        | Self::ToolResult { sequence, .. }) = &mut self;
        *sequence = value;
        self
    }
}
