// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Local execution of an immutable Control Plane decision. No discovery or policy lookup.
use std::{sync::OnceLock, time::Duration};

use fred_rust_sdk::inference::{InferenceAdmission, InferenceCredentialBinding};
use futures::{Stream, stream};
use rig_core::{
    client::CompletionClient,
    completion::{AssistantContent, CompletionModel, FinishReason},
    providers::openai,
};
use tokio::time::Instant;

use crate::RuntimeEvent;

const TURN_TIMEOUT: Duration = Duration::from_secs(120);
static HTTP: OnceLock<reqwest::Client> = OnceLock::new();

#[derive(Debug, thiserror::Error)]
pub enum InferenceError {
    #[error("Inference provisioning is missing or inconsistent.")]
    Provisioning,
    #[error("Inference credential is unavailable.")]
    Credential,
    #[error("Inference execution has ended or exceeded its deadline.")]
    Ended,
    #[error("The inference provider is unavailable or returned an invalid response.")]
    Provider,
}

/// Owned by one turn; the credential and all model options are fixed at construction.
pub struct InferenceTurn {
    admission: InferenceAdmission,
    model: openai::CompletionModel,
    deadline: Instant,
    ended: bool,
    span: tracing::Span,
}

impl InferenceTurn {
    pub fn admit(
        admission: InferenceAdmission,
        bindings: &[InferenceCredentialBinding],
    ) -> Result<Self, InferenceError> {
        Self::provision(admission, bindings, |name| std::env::var(name).ok())
    }

    fn provision(
        admission: InferenceAdmission,
        bindings: &[InferenceCredentialBinding],
        read: impl FnOnce(&str) -> Option<String>,
    ) -> Result<Self, InferenceError> {
        let mut matching = bindings
            .iter()
            .filter(|b| b.source_id == admission.selection.key.source_id);
        let local = matching.next().ok_or(InferenceError::Provisioning)?;
        let selection = &admission.selection;
        let options = &selection.options;
        if matching.next().is_some()
            || !local.matches(&admission)
            || selection.key.upstream_model_id.trim().is_empty()
            || selection.policy_revision <= 0
            || selection.snapshot_revision <= 0
            || options.temperature.is_some_and(|v| !v.is_finite())
            || options
                .top_p
                .is_some_and(|v| !v.is_finite() || !(0.0..=1.0).contains(&v))
            || options.max_tokens == Some(0)
        {
            return Err(InferenceError::Provisioning);
        }
        // Resolve only after checking source, destination, binding and exact revision.
        let secret = read(&local.api_key_env)
            .filter(|s| !s.is_empty())
            .ok_or(InferenceError::Credential)?;
        let http = if let Some(http) = HTTP.get() {
            http.clone()
        } else {
            let http = reqwest::Client::builder()
                .redirect(reqwest::redirect::Policy::none())
                .connect_timeout(Duration::from_secs(5))
                .timeout(Duration::from_secs(60))
                .pool_max_idle_per_host(32)
                .build()
                .map_err(|_| InferenceError::Provider)?;
            let _ = HTTP.set(http.clone());
            HTTP.get().cloned().unwrap_or(http)
        };
        let client = openai::Client::builder()
            .api_key(secret)
            .base_url(admission.connection.api_root.trim_end_matches('/'))
            .http_client(http)
            .build()
            .map_err(|_| InferenceError::Provider)?
            .completions_api();
        let model = client.completion_model(&selection.key.upstream_model_id);
        Ok(Self {
            admission,
            model,
            deadline: Instant::now() + TURN_TIMEOUT,
            ended: false,
            span: tracing::Span::current(),
        })
    }

    pub fn close(&mut self) {
        self.ended = true;
    }

    #[tracing::instrument(skip_all, parent = &self.span, name = "inference_call")]
    pub async fn complete(
        &mut self,
        input: String,
    ) -> Result<(String, &'static str), InferenceError> {
        if self.ended || Instant::now() >= self.deadline {
            return Err(InferenceError::Ended);
        }
        let selection = &self.admission.selection;
        let options = &selection.options;
        let mut extra = serde_json::Map::new();
        if let Some(top_p) = options.top_p {
            extra.insert("top_p".into(), top_p.into());
        }
        if let Some(effort) = options.reasoning_effort {
            extra.insert(
                "reasoning_effort".into(),
                serde_json::to_value(effort).map_err(|_| InferenceError::Provisioning)?,
            );
        }
        let started = Instant::now();
        let result = tokio::time::timeout_at(
            self.deadline,
            self.model
                .completion_request(input)
                .temperature_opt(options.temperature)
                .max_tokens_opt(options.max_tokens)
                .additional_params(serde_json::Value::Object(extra))
                .send(),
        )
        .await;
        // No provider error/body, URL, credential or prompt is recorded.
        tracing::info!(target: "control_plane::inference", source_id = %selection.key.source_id, model = %selection.key.upstream_model_id,
            policy_revision = selection.policy_revision, source_revision = selection.source_revision,
            snapshot_revision = selection.snapshot_revision, selection = ?selection.source,
            latency_ms = started.elapsed().as_millis() as u64, "Inference completed");
        let response = match result {
            Ok(Ok(response)) => response,
            Ok(Err(_)) => {
                self.close();
                return Err(InferenceError::Provider);
            }
            Err(_) => {
                self.close();
                return Err(InferenceError::Ended);
            }
        };
        let finish_reason = match response.finish_reason() {
            Some(FinishReason::Stop) => "stop",
            Some(FinishReason::Length) => "length",
            Some(FinishReason::ContentFilter) => "content_filter",
            _ => "other",
        };
        let content: String = response
            .choice
            .into_iter()
            .filter_map(|part| match part {
                AssistantContent::Text(text) => Some(text.text),
                _ => None,
            })
            .collect();
        if content.is_empty() {
            self.close();
            return Err(InferenceError::Provider);
        }
        Ok((content, finish_reason))
    }
}

/// Dropping this stream drops the in-flight request; there is no detached producer.
/// Only a managed host admission can construct its inference turn.
pub fn execute(turn: InferenceTurn, input: String) -> impl Stream<Item = RuntimeEvent> + Send {
    stream::unfold(
        (Some(turn), Some(input), 0u8, None),
        |(mut turn, mut input, step, content)| async move {
            match step {
                0 => Some((
                    RuntimeEvent::Status {
                        sequence: 1,
                        status: "running",
                    },
                    (turn, input, 1, content),
                )),
                1 => {
                    let active = turn.as_mut()?;
                    let result = active.complete(input.take()?).await;
                    active.close();
                    match result {
                        Ok((text, reason)) => Some((
                            RuntimeEvent::AssistantDelta {
                                sequence: 2,
                                delta: text.clone(),
                            },
                            (None, None, 2, Some((text, reason))),
                        )),
                        Err(_) => Some((
                            RuntimeEvent::Error {
                                sequence: 2,
                                message: "Inference failed or exceeded its deadline.",
                            },
                            (None, None, 3, None),
                        )),
                    }
                }
                2 => {
                    let (text, reason) = content?;
                    Some((
                        RuntimeEvent::Final {
                            sequence: 3,
                            content: text,
                            finish_reason: reason,
                        },
                        (None, None, 4, None),
                    ))
                }
                // Fred's error event is terminal, like the Python runtime contract.
                _ => None,
            }
        },
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{Json, Router, http::HeaderMap, routing::post};
    use futures::StreamExt;
    use serde_json::{Value, json};
    use std::sync::{Arc, Mutex};

    fn admission() -> InferenceAdmission {
        serde_json::from_str(include_str!(
            "../../../../libs/fred-sdk/tests/fixtures/inference_admission.json"
        ))
        .unwrap()
    }
    fn provisioning(a: &InferenceAdmission) -> InferenceCredentialBinding {
        InferenceCredentialBinding {
            source_id: a.selection.key.source_id.clone(),
            source_revision: 1,
            api_root: a.connection.api_root.clone(),
            credential_binding: a.connection.credential_binding.clone(),
            api_key_env: "FRED_TEST_INFERENCE_CREDENTIAL".into(),
        }
    }
    struct Provider {
        url: String,
        calls: Arc<Mutex<Vec<(HeaderMap, Value)>>>,
        task: tokio::task::JoinHandle<()>,
    }
    impl Drop for Provider {
        fn drop(&mut self) {
            self.task.abort();
        }
    }
    impl Provider {
        async fn start(delay: Duration, status: u16) -> Self {
            let calls = Arc::new(Mutex::new(Vec::new()));
            let captured = calls.clone();
            let app = Router::new().route("/v1/chat/completions", post(move |headers: HeaderMap, Json(body): Json<Value>| {
                let captured = captured.clone();
                async move {
                    captured.lock().unwrap().push((headers, body));
                    tokio::time::sleep(delay).await;
                    (axum::http::StatusCode::from_u16(status).unwrap(), Json(json!({
                        "id":"completion-fixture", "object":"chat.completion", "created":0, "model":"model",
                        "choices":[{"index":0,"message":{"role":"assistant","content":"simulated answer"},"finish_reason":"stop"}],
                        "usage":{"prompt_tokens":2,"completion_tokens":2,"total_tokens":4}
                    })))
                }
            }));
            let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
            let url = format!("http://{}/v1", listener.local_addr().unwrap());
            let task = tokio::spawn(async move {
                axum::serve(listener, app).await.unwrap();
            });
            Self { url, calls, task }
        }
        fn turn(&self) -> InferenceTurn {
            let mut a = admission();
            a.connection.api_root = self.url.clone();
            let local = provisioning(&a);
            InferenceTurn::provision(a, &[local], |_| Some("synthetic-inference-key".into()))
                .unwrap()
        }
    }

    #[tokio::test]
    async fn rig_consumes_the_shared_decision_and_freezes_it_for_the_turn() {
        let provider = Provider::start(Duration::ZERO, 200).await;
        let mut turn = provider.turn();
        for _ in 0..2 {
            assert_eq!(
                turn.complete("fixture question".into()).await.unwrap(),
                ("simulated answer".into(), "stop")
            );
        }
        turn.close();
        assert!(matches!(
            turn.complete("after termination".into()).await,
            Err(InferenceError::Ended)
        ));
        let calls = provider.calls.lock().unwrap();
        assert_eq!(calls.len(), 2);
        for (headers, body) in calls.iter() {
            assert_eq!(headers["authorization"], "Bearer synthetic-inference-key");
            assert_eq!(body["model"], "model");
            assert_eq!(body["temperature"], 0.2);
            assert_eq!(body["top_p"], 0.8);
            assert_eq!(body["max_tokens"], 50);
            assert_eq!(body["reasoning_effort"], "high");
            assert_eq!(body["messages"][0]["content"], "fixture question");
        }
    }

    #[test]
    fn mismatch_or_missing_provisioning_is_rejected_before_secret_read() {
        for field in [
            "source",
            "destination",
            "binding",
            "revision",
            "missing",
            "duplicate",
        ] {
            let a = admission();
            let mut local = provisioning(&a);
            match field {
                "source" => local.source_id = "other".into(),
                "destination" => local.api_root = "https://elsewhere.invalid/v1".into(),
                "binding" => local.credential_binding = "other".into(),
                "revision" => local.source_revision = 2,
                _ => {}
            }
            let locals = match field {
                "missing" => vec![],
                "duplicate" => vec![local.clone(), local],
                _ => vec![local],
            };
            assert!(matches!(
                InferenceTurn::provision(a, &locals, |_| panic!("must not read a credential")),
                Err(InferenceError::Provisioning)
            ));
        }
        let a = admission();
        let local = provisioning(&a);
        assert!(matches!(
            InferenceTurn::provision(a, &[local], |_| None),
            Err(InferenceError::Credential)
        ));
    }

    #[tokio::test]
    async fn stream_uses_real_rig_response_and_finishes_once() {
        let provider = Provider::start(Duration::ZERO, 200).await;
        let events: Vec<_> = execute(provider.turn(), "question".into()).collect().await;
        assert_eq!(events.len(), 3);
        assert!(
            matches!(&events[2], RuntimeEvent::Final { content, .. } if content == "simulated answer")
        );
        assert_eq!(provider.calls.lock().unwrap().len(), 1);
        let failing = Provider::start(Duration::ZERO, 401).await;
        let events: Vec<_> = execute(failing.turn(), "question".into()).collect().await;
        assert_eq!(events.len(), 2);
        assert!(matches!(&events[1], RuntimeEvent::Error { .. }));
    }

    #[tokio::test]
    async fn cancellation_before_invocation_and_during_http_drops_the_producer() {
        let provider = Provider::start(Duration::from_secs(60), 200).await;
        let mut events = Box::pin(execute(provider.turn(), "question".into()));
        assert!(matches!(
            events.next().await,
            Some(RuntimeEvent::Status { .. })
        ));
        drop(events);
        assert!(provider.calls.lock().unwrap().is_empty());
        let mut events = Box::pin(execute(provider.turn(), "question".into()));
        events.next().await;
        assert!(
            tokio::time::timeout(Duration::from_millis(100), events.next())
                .await
                .is_err()
        );
        drop(events);
        assert_eq!(provider.calls.lock().unwrap().len(), 1);
        let mut turn = provider.turn();
        turn.deadline = Instant::now();
        assert!(matches!(
            turn.complete("late".into()).await,
            Err(InferenceError::Ended)
        ));
        assert_eq!(provider.calls.lock().unwrap().len(), 1);
        let mut turn = provider.turn();
        turn.deadline = Instant::now() + Duration::from_millis(20);
        assert!(matches!(
            turn.complete("deadline in flight".into()).await,
            Err(InferenceError::Ended)
        ));
        assert!(matches!(
            turn.complete("retry after deadline".into()).await,
            Err(InferenceError::Ended)
        ));
        assert_eq!(provider.calls.lock().unwrap().len(), 2);
    }
}
