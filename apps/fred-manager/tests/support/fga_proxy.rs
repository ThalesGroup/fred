//! Fault injection around real OpenFGA acknowledgments, without replacing authorization.
use super::Gate;
use axum::{
    Router,
    body::{Body, to_bytes},
    http::{Request, Response, StatusCode},
    routing::any,
};
use std::sync::Arc;
use tokio::sync::Mutex;
#[derive(Default)]
pub struct Fault {
    pub hide_stores: bool,
    pub writes: usize,
    pub calls: std::collections::BTreeMap<String, usize>,
    pub acknowledged: Vec<u16>,
    pub fail_at: usize,
    pub after: bool,
    pub gate: Option<Arc<Gate>>,
    /// Hold the request before forwarding it, to model a write arriving after timeout.
    pub gate_before: bool,
    pub gate_role_write: bool,
    pub written: Vec<serde_json::Value>,
    pub reads: Vec<serde_json::Value>,
    pub read_page_size: Option<u64>,
}
pub struct Proxy {
    pub base: String,
    pub fault: Arc<Mutex<Fault>>,
    task: tokio::task::JoinHandle<()>,
}
impl Drop for Proxy {
    fn drop(&mut self) {
        self.task.abort();
    }
}
impl Proxy {
    pub async fn start(upstream: &str) -> Self {
        let fault = Arc::new(Mutex::new(Fault::default()));
        let state = fault.clone();
        let upstream = upstream.to_owned();
        let http = reqwest::Client::new();
        let app = Router::new().route(
            "/{*path}",
            any(move |request: Request<Body>| {
                let state = state.clone();
                let upstream = upstream.clone();
                let http = http.clone();
                async move {
                    let (parts, body) = request.into_parts();
                    let mut body = to_bytes(body, 1024 * 1024).await.unwrap();
                    if parts.uri.path().ends_with("/read") {
                        let mut value: serde_json::Value = serde_json::from_slice(&body).unwrap();
                        let mut fault = state.lock().await;
                        if let Some(size) = fault.read_page_size {
                            value["page_size"] = size.into();
                        }
                        fault.reads.push(value.clone());
                        body = serde_json::to_vec(&value).unwrap().into();
                    }
                    *state
                        .lock()
                        .await
                        .calls
                        .entry(parts.uri.path().rsplit('/').next().unwrap().into())
                        .or_default() += 1;
                    if parts.method == axum::http::Method::GET
                        && parts.uri.path() == "/stores"
                        && state.lock().await.hide_stores
                    {
                        return Response::builder()
                            .status(StatusCode::OK)
                            .header("content-type", "application/json")
                            .body(Body::from(r#"{"stores":[]}"#))
                            .unwrap();
                    }
                    let write = parts.uri.path().ends_with("/write");
                    let (fail, after, gate, gate_before) = if write {
                        let mut fault = state.lock().await;
                        fault.writes += 1;
                        let value: serde_json::Value = serde_json::from_slice(&body).unwrap();
                        let role_write =
                            value["writes"]["tuple_keys"]
                                .as_array()
                                .is_some_and(|keys| {
                                    keys.iter().any(|k| {
                                        k["object"]
                                            .as_str()
                                            .is_some_and(|o| o.starts_with("space:"))
                                    })
                                });
                        fault.written.push(value);
                        let gate = if !fault.gate_role_write || role_write {
                            fault.gate.take()
                        } else {
                            None
                        };
                        (
                            fault.writes == fault.fail_at,
                            fault.after,
                            gate,
                            fault.gate_before,
                        )
                    } else {
                        (false, false, None, false)
                    };
                    let deliver = async move {
                        if gate_before && let Some(gate) = &gate {
                            gate.entered.notify_one();
                            gate.release.notified().await;
                        }
                        if fail && !after {
                            return Response::builder()
                                .status(StatusCode::INTERNAL_SERVER_ERROR)
                                .body(Body::from("private-password"))
                                .unwrap();
                        }
                        let reply = http
                            .request(parts.method, format!("{upstream}{}", parts.uri))
                            .header("content-type", "application/json")
                            .body(body)
                            .send()
                            .await
                            .unwrap();
                        let status = reply.status();
                        if write {
                            state.lock().await.acknowledged.push(status.as_u16());
                        }
                        let body = reply.bytes().await.unwrap();
                        if !gate_before && let Some(gate) = gate {
                            gate.entered.notify_one();
                            gate.release.notified().await;
                        }
                        if fail {
                            return Response::builder()
                                .status(StatusCode::INTERNAL_SERVER_ERROR)
                                .body(Body::from("private-password"))
                                .unwrap();
                        }
                        Response::builder()
                            .status(status)
                            .header("content-type", "application/json")
                            .body(Body::from(body))
                            .unwrap()
                    };
                    if gate_before {
                        // Model an accepted request whose cancellation does not reach
                        // the upstream: its delivery survives the caller disconnect.
                        tokio::spawn(deliver).await.unwrap()
                    } else {
                        deliver.await
                    }
                }
            }),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let base = format!("http://{}", listener.local_addr().unwrap());
        let task = tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        Self { base, fault, task }
    }
}
