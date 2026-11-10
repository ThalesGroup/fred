// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

//! Control Plane's request logging and role audit on the shared stdout format.

use std::time::Instant;

use axum::{
    extract::{MatchedPath, Request},
    http::HeaderValue,
    middleware::Next,
    response::Response,
};
use fred_rust_sdk::logging::{AUDIT_TARGET, LogIdentity};
pub use fred_rust_sdk::logging::{HTTP_TARGET, LogFormat};
use tracing::{Instrument, Level};
use uuid::Uuid;

/// `role` is `api` for the server, `migration` or `job` for a one-shot command.
pub fn identity(role: &'static str) -> LogIdentity {
    LogIdentity {
        service: "control-plane",
        role,
        owner: "control_plane",
    }
}

#[derive(Clone)]
struct RouteTemplate(String);

/// Inner layer: hands the matched route template out to `request_logging`.
pub async fn expose_route(request: Request, next: Next) -> Response {
    let route = request
        .extensions()
        .get::<MatchedPath>()
        .map(|p| p.as_str().to_string());
    let mut response = next.run(request).await;
    if let Some(route) = route {
        response.extensions_mut().insert(RouteTemplate(route));
    }
    response
}

/// fred-core `RequestLoggingMiddleware`: request and correlation ids on every log line of
/// the request and in the response headers, then one completion event on `http`.
pub async fn request_logging(request: Request, next: Next) -> Response {
    let (request_id, correlation_id) = (Uuid::new_v4(), Uuid::new_v4());
    let span = tracing::info_span!(
        "request",
        request_id = %request_id,
        correlation_id = %correlation_id,
        user_id = tracing::field::Empty,
    );
    let mut completion = Completion {
        method: request.method().to_string(),
        path: request.uri().path().to_string(),
        started: Instant::now(),
        span: span.clone(),
        done: false,
    };
    let mut response = next.run(request).instrument(span).await;
    let headers = response.headers_mut();
    for (name, id) in [
        ("x-request-id", request_id),
        ("x-correlation-id", correlation_id),
    ] {
        if let Ok(value) = HeaderValue::from_str(&id.to_string()) {
            headers.insert(name, value);
        }
    }
    let route = response
        .extensions()
        .get::<RouteTemplate>()
        .map(|r| r.0.clone());
    completion.finish(route, Some(response.status().as_u16()), "responded");
    response
}

/// Routes the workers poll every few seconds. A successful poll is routine: DEBUG, so
/// INFO keeps the requests that act. Failures keep WARN/ERROR; the work found is
/// logged by its own handler and report.
const POLLED_ROUTES: [&str; 2] = [
    "/capability-preparations/cleanup",
    "/document-processing/cleanup",
];

struct Completion {
    method: String,
    path: String,
    started: Instant,
    span: tracing::Span,
    done: bool,
}

impl Completion {
    fn finish(&mut self, route: Option<String>, status: Option<u16>, outcome: &str) {
        self.done = true;
        let successful = outcome == "responded" && status.is_some_and(|s| s < 400);
        if successful && (self.path.ends_with("/healthz") || self.path.ends_with("/ready")) {
            return;
        }
        let duration_ms = self.started.elapsed().as_secs_f64() * 1000.0;
        let route_label = route.clone().unwrap_or_else(|| "<unmatched>".into());
        let status_label = status.map_or("no response".to_string(), |s| s.to_string());
        let suffix = if outcome == "responded" {
            String::new()
        } else {
            format!(" | {outcome}")
        };
        let message = format!(
            "{} {route_label} → {status_label} | {duration_ms:.0}ms{suffix}",
            self.method
        );
        let _entered = self.span.enter();
        let route = route.unwrap_or_default();
        let http_status = status.map(u64::from);
        macro_rules! completion {
            ($level:expr) => {
                tracing::event!(
                    target: "http",
                    $level,
                    http_method = %self.method,
                    duration_ms,
                    outcome,
                    route = %route,
                    http_status,
                    "{}",
                    message
                )
            };
        }
        if successful && self.method == "GET" && POLLED_ROUTES.iter().any(|r| route.ends_with(r)) {
            completion!(Level::DEBUG);
        } else if successful {
            completion!(Level::INFO);
        } else if status.is_some_and(|s| s >= 500) || outcome == "failed" {
            completion!(Level::ERROR);
        } else {
            completion!(Level::WARN);
        }
    }
}

/// A request whose future is dropped before responding: the client went away.
impl Drop for Completion {
    fn drop(&mut self) {
        if !self.done {
            self.finish(None, None, "cancelled");
        }
    }
}

/// Fred's security stream records role changes,
/// independently of a later SQL commit. No fabricated actor for operator-only calls.
pub(crate) fn audit_relation(
    actor: Option<&str>,
    target: &str,
    relation: &str,
    resource: &str,
    grant: bool,
) {
    let event = if grant {
        "authz.relation.granted"
    } else {
        "authz.relation.revoked"
    };
    tracing::info!(target: AUDIT_TARGET, audit_event = event, actor_uid = actor,
        subject = format!("user:{target}"), relation, resource, outcome = "succeeded", "[SECURITY] {event}");
}

#[cfg(test)]
mod tests {
    use super::*;
    use fred_rust_sdk::logging::StdoutLayer;
    use serde_json::Value;
    use std::{
        io::Write,
        sync::{Arc, Mutex},
    };
    use tracing_subscriber::prelude::*;

    #[derive(Clone, Default)]
    struct Buffer(Arc<Mutex<Vec<u8>>>);

    impl Write for Buffer {
        fn write(&mut self, data: &[u8]) -> std::io::Result<usize> {
            self.0.lock().unwrap().extend_from_slice(data);
            Ok(data.len())
        }
        fn flush(&mut self) -> std::io::Result<()> {
            Ok(())
        }
    }

    // Proves: I16
    #[test]
    fn audit_relation_writes_the_role_change_fields() {
        let buffer = Buffer::default();
        let sink = buffer.clone();
        let subscriber = tracing_subscriber::registry().with(StdoutLayer::new(
            identity("api"),
            LogFormat::Text,
            false,
            move || sink,
        ));
        tracing::subscriber::with_default(subscriber, || {
            audit_relation(Some("actor-sub"), "target-sub", "analyst", "space:s1", true);
        });
        let output = String::from_utf8(buffer.0.lock().unwrap().clone()).unwrap();
        let line: Value = serde_json::from_str(output.trim()).unwrap();
        assert_eq!(line["logger"], AUDIT_TARGET);
        assert_eq!(line["audit_event"], "authz.relation.granted");
        assert_eq!(line["actor_uid"], "actor-sub");
        assert_eq!(line["subject"], "user:target-sub");
        assert_eq!(line["relation"], "analyst");
        assert_eq!(line["resource"], "space:s1");
        assert_eq!(line["outcome"], "succeeded");
    }

    // Proves: I13
    #[tokio::test]
    async fn requests_carry_ids_and_end_with_one_http_event() {
        use axum::{Router, body::Body, routing::get};
        use tower::ServiceExt;

        let buffer = Buffer::default();
        let sink = buffer.clone();
        let subscriber = tracing_subscriber::registry().with(StdoutLayer::new(
            identity("api"),
            LogFormat::Json,
            false,
            move || sink,
        ));
        let _guard = tracing::subscriber::set_default(subscriber);
        let app = Router::new()
            .route(
                "/spaces/{id}",
                get(|| async {
                    tracing::info!("in handler");
                    "ok"
                }),
            )
            .route("/healthz", get(|| async { "ok" }))
            .route_layer(axum::middleware::from_fn(expose_route))
            .layer(axum::middleware::from_fn(request_logging));

        let request = |uri: &str| Request::builder().uri(uri).body(Body::empty()).unwrap();
        let response = app.clone().oneshot(request("/spaces/42")).await.unwrap();
        let request_id = response.headers()["x-request-id"]
            .to_str()
            .unwrap()
            .to_string();
        assert!(response.headers().contains_key("x-correlation-id"));
        app.oneshot(request("/healthz")).await.unwrap();

        let text = String::from_utf8(buffer.0.lock().unwrap().clone()).unwrap();
        let lines: Vec<Value> = text
            .lines()
            .map(|l| serde_json::from_str(l).unwrap())
            .collect();
        assert_eq!(
            lines.len(),
            2,
            "handler line and one completion, no healthz: {text}"
        );
        assert_eq!(lines[0]["message"], "in handler");
        let done = &lines[1];
        assert_eq!(done["logger"], "http");
        assert_eq!(done["severity"], "INFO");
        assert_eq!(done["route"], "/spaces/{id}");
        assert_eq!(done["http_status"], 200);
        assert_eq!(done["outcome"], "responded");
        for line in &lines {
            assert_eq!(line["request_id"], request_id.as_str());
        }
    }

    #[tokio::test]
    async fn a_successful_worker_poll_is_debug_and_its_report_stays_info() {
        use axum::{Router, body::Body, http::Method, routing::get};
        use tower::ServiceExt;

        let buffer = Buffer::default();
        let sink = buffer.clone();
        let subscriber = tracing_subscriber::registry().with(StdoutLayer::new(
            identity("api"),
            LogFormat::Json,
            false,
            move || sink,
        ));
        let _guard = tracing::subscriber::set_default(subscriber);
        let app = Router::new()
            .route(
                "/document-processing/cleanup",
                get(|| async { "[]" }).post(|| async { "ok" }),
            )
            .route_layer(axum::middleware::from_fn(expose_route))
            .layer(axum::middleware::from_fn(request_logging));
        let request = |method: Method| {
            Request::builder()
                .method(method)
                .uri("/document-processing/cleanup")
                .body(Body::empty())
                .unwrap()
        };
        app.clone().oneshot(request(Method::GET)).await.unwrap();
        app.oneshot(request(Method::POST)).await.unwrap();

        let text = String::from_utf8(buffer.0.lock().unwrap().clone()).unwrap();
        let severities: Vec<String> = text
            .lines()
            .map(|l| serde_json::from_str::<Value>(l).unwrap()["severity"].to_string())
            .collect();
        assert_eq!(severities, ["\"DEBUG\"", "\"INFO\""], "{text}");
    }
}
