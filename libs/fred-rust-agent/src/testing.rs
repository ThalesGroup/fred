// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! A loopback provider speaking SSE when asked to stream, as a real one does, so the
//! tests exercise Rig's real agent and HTTP adapter.

use std::{
    sync::{Arc, Mutex},
    time::Duration,
};

use axum::{
    Json, Router,
    body::Body,
    http::{HeaderMap, Uri},
    response::{IntoResponse, Response},
    routing::post,
};
use fred_rust_sdk::inference::{InferenceAdmission, InferenceCredentialBinding};
use futures::StreamExt;
use serde_json::{Value, json};

use crate::turn::InferenceTurn;

pub(crate) fn admission() -> InferenceAdmission {
    serde_json::from_str(include_str!(
        "../../fred-sdk/tests/fixtures/inference_admission.json"
    ))
    .unwrap()
}
pub(crate) fn provisioning(a: &InferenceAdmission) -> InferenceCredentialBinding {
    InferenceCredentialBinding {
        credential_binding: a.connection.credential_binding.clone(),
        api_root: a.connection.api_root.clone(),
        api_key_env: "FRED_TEST_INFERENCE_CREDENTIAL".into(),
    }
}

pub(crate) fn chunk(delta: Value, finish_reason: Value, usage: Option<Value>) -> String {
    let mut chunk = json!({"id":"completion-fixture","object":"chat.completion.chunk",
            "created":0,"model":"model",
            "choices":[{"index":0,"delta":delta,"finish_reason":finish_reason}]});
    if let Some(usage) = usage {
        chunk["usage"] = usage;
    }
    format!("data: {chunk}\n\n")
}

/// A provider's SSE frames for one scripted reply: reasoning and text in fragments.
pub(crate) fn frames(response: &Value) -> Vec<String> {
    let choice = &response["choices"][0];
    let message = &choice["message"];
    let mut frames = vec![];
    if let Some(reasoning) = message.get("reasoning_content") {
        frames.push(chunk(
            json!({"role":"assistant","reasoning_content":reasoning}),
            Value::Null,
            None,
        ));
    }
    if let Some(details) = message.get("reasoning_details") {
        frames.push(chunk(
            json!({"reasoning_details":details}),
            Value::Null,
            None,
        ));
    }
    if let Some(content) = message["content"].as_str() {
        for word in content.split_inclusive(' ') {
            frames.push(chunk(
                json!({"role":"assistant","content":word}),
                Value::Null,
                None,
            ));
        }
    }
    if let Some(calls) = message["tool_calls"].as_array() {
        let calls: Vec<_> = calls
            .iter()
            .enumerate()
            .map(|(index, call)| {
                let mut call = call.clone();
                call["index"] = json!(index);
                call
            })
            .collect();
        frames.push(chunk(
            json!({"role":"assistant","tool_calls":calls}),
            Value::Null,
            None,
        ));
    }
    if response.get("truncated").is_none() {
        frames.push(chunk(
            json!({}),
            choice["finish_reason"].clone(),
            Some(json!({"prompt_tokens":2,"completion_tokens":2,"total_tokens":4})),
        ));
        frames.push("data: [DONE]\n\n".into());
    }
    frames
}

/// Replies as a provider does: in SSE when asked to stream, in JSON otherwise.
pub(crate) fn reply(status: u16, mut response: Value, stream: bool) -> Response {
    let status = axum::http::StatusCode::from_u16(status).unwrap();
    if stream && status.is_success() {
        let gap = response["gap_ms"].as_u64().unwrap_or(0);
        let body = futures::stream::iter(frames(&response).into_iter().enumerate()).then(
            move |(index, frame)| async move {
                if index > 0 && gap > 0 {
                    tokio::time::sleep(Duration::from_millis(gap)).await;
                }
                Ok::<_, std::convert::Infallible>(frame)
            },
        );
        return (
            status,
            [("content-type", "text/event-stream")],
            Body::from_stream(body),
        )
            .into_response();
    }
    response["id"] = json!("completion-fixture");
    response["object"] = json!("chat.completion");
    response["created"] = json!(0);
    response["model"] = json!("model");
    response["usage"] = json!({"prompt_tokens":2,"completion_tokens":2,"total_tokens":4});
    (status, Json(response)).into_response()
}

pub(crate) struct Provider {
    pub(crate) url: String,
    pub(crate) calls: Arc<Mutex<Vec<(HeaderMap, Value)>>>,
    /// Path and query of every request, as received.
    pub(crate) uris: Arc<Mutex<Vec<String>>>,
    task: tokio::task::JoinHandle<()>,
}
impl Drop for Provider {
    fn drop(&mut self) {
        self.task.abort();
    }
}
impl Provider {
    pub(crate) async fn start(delay: Duration, status: u16) -> Self {
        Self::with_response(delay, status, "simulated answer", "stop").await
    }
    pub(crate) async fn with_response(
        delay: Duration,
        status: u16,
        content: &'static str,
        reason: &'static str,
    ) -> Self {
        Self::script(vec![(delay, status, json!({
                "choices":[{"index":0,"message":{"role":"assistant","content":content},"finish_reason":reason}]
            }))]).await
    }
    pub(crate) async fn script(responses: Vec<(Duration, u16, Value)>) -> Self {
        Self::script_at("/v1", responses).await
    }
    /// Answers only on `{root}/chat/completions`: any other path gets a 404.
    pub(crate) async fn at(root: &str) -> Self {
        let answer = json!({"choices":[{"index":0,"message":{"role":"assistant",
            "content":"simulated answer"},"finish_reason":"stop"}]});
        Self::script_at(root, vec![(Duration::ZERO, 200, answer)]).await
    }
    async fn script_at(root: &str, responses: Vec<(Duration, u16, Value)>) -> Self {
        let responses = Arc::new(Mutex::new(std::collections::VecDeque::from(responses)));
        let calls = Arc::new(Mutex::new(Vec::new()));
        let captured = calls.clone();
        let uris = Arc::new(Mutex::new(Vec::new()));
        let received = uris.clone();
        let app = Router::new().route(
            &format!("{root}/chat/completions"),
            post(
                move |uri: Uri, headers: HeaderMap, Json(body): Json<Value>| {
                    let captured = captured.clone();
                    let received = received.clone();
                    let responses = responses.clone();
                    async move {
                        let stream = body["stream"] == true;
                        received.lock().unwrap().push(uri.to_string());
                        captured.lock().unwrap().push((headers, body));
                        let (delay, status, response) = {
                            let mut responses = responses.lock().unwrap();
                            if responses.len() > 1 {
                                responses.pop_front().unwrap()
                            } else {
                                responses.front().unwrap().clone()
                            }
                        };
                        tokio::time::sleep(delay).await;
                        reply(status, response, stream)
                    }
                },
            ),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let url = format!("http://{}{root}", listener.local_addr().unwrap());
        let task = tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        Self {
            url,
            calls,
            uris,
            task,
        }
    }
    pub(crate) fn turn(&self) -> InferenceTurn {
        let mut a = admission();
        a.connection.api_root = self.url.clone();
        self.turn_for(a)
    }
    pub(crate) fn turn_for(&self, a: InferenceAdmission) -> InferenceTurn {
        let local = provisioning(&a);
        InferenceTurn::provision(a, &[local], |_| Some("synthetic-inference-key".into())).unwrap()
    }
}
