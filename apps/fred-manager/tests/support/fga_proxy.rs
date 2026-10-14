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
    pub writes: usize,
    pub acknowledged: Vec<u16>,
    pub fail_at: usize,
    pub after: bool,
    pub gate: Option<Arc<Gate>>,
    pub written: Vec<serde_json::Value>,
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
                    let body = to_bytes(body, 1024 * 1024).await.unwrap();
                    let write = parts.uri.path().ends_with("/write");
                    let (fail, after, gate) = if write {
                        let mut fault = state.lock().await;
                        fault.writes += 1;
                        fault.written.push(serde_json::from_slice(&body).unwrap());
                        (
                            fault.writes == fault.fail_at,
                            fault.after,
                            fault.gate.take(),
                        )
                    } else {
                        (false, false, None)
                    };
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
                    if let Some(gate) = gate {
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
