// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! The execution request Ralph accepts: a validated shape, not authority.

use std::collections::BTreeMap;

use fred_rust_sdk::inference::ModelOfferKey;
use serde::Deserialize;
use serde_json::Value;

use crate::AGENT_ID;

// Subset of fred-sdk/contracts/execution.py::RuntimeExecuteRequest accepted by Ralph.
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
                // Browser correlation only; no steering or resume is implemented.
                "steering_turn_id" => {
                    value.is_null()
                        || value
                            .as_str()
                            .is_some_and(|id| !id.is_empty() && id.len() <= 128)
                }
                _ => false,
            };
            if !supported_default {
                return Err(ExecuteError::Invalid(
                    "Unsupported execution option for Ralph.",
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
            if context.keys().any(|key| {
                !matches!(
                    key.as_str(),
                    "space_id" | "model_choice" | "reasoning" | "language"
                )
            }) {
                return Err(ExecuteError::Invalid(
                    "Unsupported runtime context for embedded execution.",
                ));
            }
            // Display metadata sent by the existing chat, never execution authority.
            if context.get("language").is_some_and(|value| {
                !value.is_null() && !value.as_str().is_some_and(|language| language.len() <= 64)
            }) {
                return Err(ExecuteError::Invalid("Invalid language."));
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

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn browser_envelope_accepts_metadata_without_enabling_extra_execution_features() {
        let body = json!({
            "agent_instance_id":"instance", "input":"Bonjour", "session_id":"session",
            "steering_turn_id":"turn", "runtime_context":{"space_id":"space","language":"fr"}
        });
        let request: ExecuteRequest = serde_json::from_value(body.clone()).unwrap();
        assert!(matches!(
            request.validate(),
            Ok(RequestedTarget::Managed { .. })
        ));
        for (key, value) in [
            ("resume_payload", json!({"answer":"yes"})),
            ("turn_options", json!({"document_selection":{}})),
            ("invocation_turns", json!([{"input":"previous"}])),
            ("steering_turn_id", json!({"invalid":true})),
        ] {
            let mut unsupported = body.clone();
            unsupported[key] = value;
            let request: ExecuteRequest = serde_json::from_value(unsupported).unwrap();
            assert!(request.validate().is_err(), "{key}");
        }
        let mut unsupported = body;
        unsupported["runtime_context"]["document_scope"] = json!({});
        let request: ExecuteRequest = serde_json::from_value(unsupported).unwrap();
        assert!(request.validate().is_err());
    }
}
