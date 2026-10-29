// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
//! Consume KF's exported submission policy. Python's existing models own this contract.
use super::models::Profile;
use anyhow::{Result, ensure};
use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use serde::Deserialize;
use serde_json::{Value, json};
use uuid::Uuid;

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WorkerContract {
    pub workflow: String,
    pub schema: Value,
    pub processor_profiles: std::collections::HashMap<String, Value>,
    pub profiles: std::collections::HashMap<String, Value>,
}
impl WorkerContract {
    pub fn load(path: &str, queue: &str) -> Result<Self> {
        use std::io::Read;
        let mut bytes = Vec::new();
        std::fs::File::open(path)?
            .take(262145)
            .read_to_end(&mut bytes)?;
        ensure!(bytes.len() <= 262144, "KF contract export is too large");
        let contract: Self = serde_json::from_slice(&bytes)?;
        ensure!(
            contract.workflow == "ProcessPush"
                && contract.schema.get("title").and_then(Value::as_str)
                    == Some("PipelineDefinition"),
            "expected the existing KF ProcessPush contract"
        );
        for profile in ["fast", "medium", "rich"] {
            ensure!(
                contract
                    .processor_profiles
                    .get(profile)
                    .is_some_and(Value::is_object),
                "missing KF processor profile"
            );
            let policy = contract
                .profiles
                .get(profile)
                .and_then(Value::as_object)
                .ok_or_else(|| anyhow::anyhow!("missing KF submission policy"))?;
            ensure!(
                policy.get("extraction_task_queue").and_then(Value::as_str)
                    == Some(&format!("{queue}-{profile}")),
                "KF extraction queue differs from manager queue"
            );
            ensure!(
                policy.len() == 11
                    && policy.keys().all(|key| matches!(
                        key.as_str(),
                        "extraction_task_queue"
                            | "push_metadata_activity_timeout_seconds"
                            | "pull_metadata_activity_timeout_seconds"
                            | "output_activity_timeout_seconds"
                            | "input_activity_timeout_seconds"
                            | "heartbeat_timeout_seconds"
                            | "retry_initial_interval_seconds"
                            | "retry_backoff_coefficient"
                            | "retry_maximum_interval_seconds"
                            | "retry_maximum_attempts"
                            | "retry_non_retryable_error_types"
                    )),
                "invalid KF submission policy fields"
            );
            for (key, value) in policy {
                match key.as_str() {
                    "extraction_task_queue" => (),
                    "retry_non_retryable_error_types" => ensure!(
                        value.as_array().is_some_and(|a| a.len() <= 100
                            && a.iter().all(|v| v.as_str().is_some_and(|s| s.len() <= 256))),
                        "invalid KF retry error types"
                    ),
                    "retry_backoff_coefficient" => ensure!(
                        value.as_f64().is_some_and(|v| v >= 1.0 && v.is_finite()),
                        "invalid KF retry backoff"
                    ),
                    _ => ensure!(
                        value.as_i64().is_some_and(|v| v > 0 && v <= 604800),
                        "invalid KF policy duration or attempt count"
                    ),
                }
            }
        }
        Ok(contract)
    }
    /// Stage leases in seconds (preparation, extraction, indexing), validated at load.
    pub fn leases(&self, profile: Profile) -> [i32; 3] {
        let policy = &self.profiles[profile.as_str()];
        [
            "push_metadata_activity_timeout_seconds",
            "input_activity_timeout_seconds",
            "output_activity_timeout_seconds",
        ]
        .map(|key| policy[key].as_i64().map_or(0, |v| v as i32))
    }
    pub fn submission(
        &self,
        installation: Uuid,
        operation: Uuid,
        document: Uuid,
        actor: &str,
        profile: Profile,
        workflow: &str,
    ) -> Value {
        // Same diagnostic envelope as fred_core.logs.propagation.encode_log_context.
        // Capture once in the durable submission, as SchedulerService does.
        let logging_context=URL_SAFE_NO_PAD.encode(serde_json::to_vec(&json!({"v":1,"context":{"correlation_id":operation.to_string(),"workflow_id":workflow,"user_id":actor}})).unwrap());
        let name = serde_json::to_value(profile).unwrap();
        let mut file = self.profiles[name.as_str().unwrap()].clone();
        let object = file.as_object_mut().unwrap();
        for (key,value) in json!({"source_tag":format!("manager:{installation}:{operation}"),"tags":[],"display_name":document.to_string(),"document_uid":document,"profile":name,"task_id":null,"logging_context":logging_context,"processed_by":{"uid":actor,"username":actor,"roles":[]}}).as_object().unwrap() {object.insert(key.clone(),value.clone());}
        json!({"workflow_id":workflow,"name":"manager-document-processing","files":[file],"max_parallelism":1,"logging_context":logging_context})
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn submission_matches_existing_python_contract_fixture() {
        let contract = WorkerContract::load(
            "tests/fixtures/processing/worker-contract.json",
            "ingestion",
        )
        .unwrap();
        let id = Uuid::from_u128(1);
        let submissions: Vec<_> = [Profile::Fast, Profile::Medium, Profile::Rich]
            .into_iter()
            .map(|profile| {
                contract.submission(id, id, id, "writer", profile, "manager-contract-test")
            })
            .collect();
        let path = "tests/fixtures/processing/submissions.json";
        if std::env::var_os("UPDATE_PROCESSING_FIXTURE").is_some() {
            std::fs::write(
                path,
                serde_json::to_string_pretty(&submissions).unwrap() + "\n",
            )
            .unwrap();
        }
        let expected: Value = serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
        assert_eq!(serde_json::to_value(submissions).unwrap(), expected);
    }
}
