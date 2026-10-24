// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Embedded hello-world runtime. The host owns HTTP, identity and admission.

use std::{collections::BTreeMap, time::Duration};

use futures::{Stream, StreamExt, stream};
use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const AGENT_ID: &str = "fred.github.ralph";

/// Descriptive metadata, independent of the host's discovery wire format.
pub struct AgentDefinition {
    pub id: &'static str,
    pub title: &'static str,
    pub version: &'static str,
    pub provider: &'static str,
    pub description: &'static str,
}

pub const DEFINITION: AgentDefinition = AgentDefinition {
    id: AGENT_ID,
    title: AGENT_ID,
    version: "0.1.0",
    provider: "control-plane",
    description: "Demonstration agent replying Hello world! without an LLM or data access.",
};

// Direct-template subset of fred-sdk/contracts/execution.py::RuntimeExecuteRequest.
#[derive(Deserialize, utoipa::ToSchema)]
pub struct ExecuteRequest {
    agent_id: Option<String>,
    agent_instance_id: Option<String>,
    #[serde(default)]
    input: String,
    session_id: Option<String>,
    runtime_context: Option<BTreeMap<String, Value>>,
    #[serde(flatten)]
    options: BTreeMap<String, Value>,
}

#[derive(Debug, thiserror::Error)]
pub enum ExecuteError {
    #[error("{0}")]
    Invalid(&'static str),
    #[error("Unknown agent_id.")]
    UnknownAgent,
    #[error("Managed execution is unavailable for the embedded hello-world agent.")]
    ManagedUnsupported,
}

impl ExecuteRequest {
    pub fn validate(&self) -> Result<(), ExecuteError> {
        if self.agent_id.is_some() == self.agent_instance_id.is_some() {
            return Err(ExecuteError::Invalid(
                "Provide exactly one of agent_id or agent_instance_id.",
            ));
        }
        if self.agent_instance_id.is_some() {
            return Err(ExecuteError::ManagedUnsupported);
        }
        if self.agent_id.as_deref() != Some(AGENT_ID) {
            return Err(ExecuteError::UnknownAgent);
        }
        if self.input.trim().is_empty() {
            return Err(ExecuteError::Invalid("input is required."));
        }
        // Accept the default envelopes sent by Fred clients, not unsupported behavior.
        for (key, value) in &self.options {
            let supported_default = match key.as_str() {
                "resume_payload" | "interrupt_id" | "occurrence_id" | "interrupted_action"
                | "interruption_id" => value.is_null(),
                "inline_tuning" => {
                    value.is_null() || value.as_object().is_some_and(|v| v.is_empty())
                }
                "turn_options" => value.as_object().is_some_and(|v| v.is_empty()),
                "invocation_turns" => value.as_array().is_some_and(|v| v.is_empty()),
                _ => false,
            };
            if !supported_default {
                return Err(ExecuteError::Invalid(
                    "Unsupported execution option for the hello-world agent.",
                ));
            }
        }
        // Session/context are accepted as wire metadata; this step has no memory or tools.
        let _ = (&self.session_id, &self.runtime_context);
        Ok(())
    }
}

// Wire subset of fred-sdk/contracts/runtime.py::RuntimeEvent.
#[derive(Serialize, utoipa::ToSchema)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum RuntimeEvent {
    Status {
        sequence: u64,
        status: &'static str,
    },
    AssistantDelta {
        sequence: u64,
        delta: &'static str,
    },
    Final {
        sequence: u64,
        content: &'static str,
        finish_reason: &'static str,
    },
}

/// Validate before sending headers, then produce one finite Fred event stream.
pub fn execute(request: ExecuteRequest) -> Result<impl Stream<Item = RuntimeEvent>, ExecuteError> {
    request.validate()?;
    // Do not retain caller metadata (which can contain credentials) during streaming.
    drop(request);
    let events = [
        RuntimeEvent::Status {
            sequence: 1,
            status: "running",
        },
        RuntimeEvent::AssistantDelta {
            sequence: 2,
            delta: "Hello ",
        },
        RuntimeEvent::AssistantDelta {
            sequence: 3,
            delta: "world!",
        },
        RuntimeEvent::Final {
            sequence: 4,
            content: "Hello world!",
            finish_reason: "stop",
        },
    ];
    // Dropping the stream cancels the async delay; there is no detached producer.
    Ok(stream::iter(events).then(|event| async move {
        if matches!(&event, RuntimeEvent::AssistantDelta { .. }) {
            tokio::time::sleep(Duration::from_millis(150)).await;
        }
        event
    }))
}
