// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Embedded hello-world runtime. The host owns HTTP, identity and admission.

use std::{collections::BTreeMap, time::Duration};

use fred_rust_sdk::inference::ModelOfferKey;
use futures::{Stream, StreamExt, stream};
use serde::{Deserialize, Serialize};
use serde_json::Value;

pub mod inference;

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
    version: env!("CARGO_PKG_VERSION"),
    provider: "control-plane",
    description: "Demonstration agent replying Hello world! without an LLM or data access.",
};

// Fixed-response subset of fred-sdk/contracts/execution.py::RuntimeExecuteRequest.
#[derive(Deserialize, utoipa::ToSchema)]
pub struct ExecuteRequest {
    agent_id: Option<String>,
    agent_instance_id: Option<String>,
    #[serde(default)]
    pub input: String,
    session_id: Option<String>,
    runtime_context: Option<BTreeMap<String, Value>>,
    #[serde(flatten)]
    options: BTreeMap<String, Value>,
}

/// Validated request shape, not authority. The host must admit managed targets.
pub enum RequestedTarget<'a> {
    Direct,
    Managed {
        instance_id: &'a str,
        space_id: &'a str,
        session_id: Option<&'a str>,
        choice: Option<ModelOfferKey>,
        reasoning: bool,
    },
}

#[derive(Debug, thiserror::Error)]
pub enum ExecuteError {
    #[error("{0}")]
    Invalid(&'static str),
    #[error("Unknown agent_id.")]
    UnknownAgent,
}

impl ExecuteRequest {
    pub fn validate(&self) -> Result<RequestedTarget<'_>, ExecuteError> {
        if self.agent_id.is_some() == self.agent_instance_id.is_some() {
            return Err(ExecuteError::Invalid(
                "Provide exactly one of agent_id or agent_instance_id.",
            ));
        }
        if self.agent_id.as_deref().is_some_and(|id| id != AGENT_ID) {
            return Err(ExecuteError::UnknownAgent);
        }
        if self.input.len() > 65_536 {
            return Err(ExecuteError::Invalid(
                "input exceeds the embedded runtime limit.",
            ));
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
        if let Some(instance_id) = self.agent_instance_id.as_deref() {
            let context = self.runtime_context.as_ref().ok_or(ExecuteError::Invalid(
                "runtime_context.space_id is required for managed execution.",
            ))?;
            let space_id = context
                .get("space_id")
                .and_then(Value::as_str)
                .filter(|id| !id.trim().is_empty())
                .ok_or(ExecuteError::Invalid(
                    "runtime_context.space_id must be a non-blank string.",
                ))?;
            if context
                .keys()
                .any(|key| !matches!(key.as_str(), "space_id" | "model_choice" | "reasoning"))
            {
                return Err(ExecuteError::Invalid(
                    "Unsupported runtime context for embedded execution.",
                ));
            }
            let choice = context
                .get("model_choice")
                .filter(|v| !v.is_null())
                .map(|v| serde_json::from_value::<ModelOfferKey>(v.clone()))
                .transpose()
                .map_err(|_| ExecuteError::Invalid("Invalid model_choice."))?;
            let reasoning = match context.get("reasoning") {
                None | Some(Value::Null) => false,
                Some(Value::Bool(value)) => *value,
                _ => return Err(ExecuteError::Invalid("reasoning must be a boolean.")),
            };
            return Ok(RequestedTarget::Managed {
                instance_id,
                space_id,
                session_id: self.session_id.as_deref(),
                choice,
                reasoning,
            });
        }
        // Direct-demo session/context remain inert metadata: no memory or tools.
        Ok(RequestedTarget::Direct)
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
        delta: String,
    },
    #[serde(rename = "execution_error")]
    Error {
        sequence: u64,
        message: &'static str,
    },
    Final {
        sequence: u64,
        content: String,
        finish_reason: &'static str,
    },
}

/// Produce the fixed response after host admission; no caller context enters the stream.
pub fn execute() -> impl Stream<Item = RuntimeEvent> {
    let events = [
        RuntimeEvent::Status {
            sequence: 1,
            status: "running",
        },
        RuntimeEvent::AssistantDelta {
            sequence: 2,
            delta: "Hello ".into(),
        },
        RuntimeEvent::AssistantDelta {
            sequence: 3,
            delta: "world!".into(),
        },
        RuntimeEvent::Final {
            sequence: 4,
            content: "Hello world!".into(),
            finish_reason: "stop",
        },
    ];
    // Dropping the stream cancels the async delay; there is no detached producer.
    stream::iter(events).then(|event| async move {
        if matches!(&event, RuntimeEvent::AssistantDelta { .. }) {
            tokio::time::sleep(Duration::from_millis(150)).await;
        }
        event
    })
}
