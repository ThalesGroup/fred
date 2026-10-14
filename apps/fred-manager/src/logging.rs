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

//! Stdout logging with the same output as fred-core `logs/processors.py`: one JSON object
//! per line (`app.log_format: json`) or readable text, the same core fields, request
//! context as top-level fields, and dependency events reduced to a fixed diagnostic.

use std::{
    io::{IsTerminal, Write},
    sync::Mutex,
    time::{Instant, SystemTime, UNIX_EPOCH},
};

use axum::{
    extract::{MatchedPath, Request},
    http::HeaderValue,
    middleware::Next,
    response::Response,
};
use serde::Deserialize;
use serde_json::{Map, Value, json};
use tracing::{
    Event, Instrument, Level, Subscriber,
    field::{Field, Visit},
    span,
};
use tracing_subscriber::{Layer, layer::Context, prelude::*, registry::LookupSpan};
use uuid::Uuid;

pub const SERVICE: &str = "fred-manager";
const ROLE: &str = "api";
/// The logger of the request completion event, as fred-core's `http` logger.
pub const HTTP_TARGET: &str = "http";

/// Core metadata that event or context fields can never replace.
const RESERVED: &[&str] = &[
    "severity",
    "message",
    "timestamp",
    "logger",
    "service",
    "service_role",
    "category",
    "file",
    "line",
    "process",
    "thread",
    "task_name",
    "host",
    "logging.googleapis.com/sourceLocation",
    "httpRequest",
    "trace_id",
    "span_id",
    "ts",
    "level",
    "msg",
    "exception",
    "stack",
    "event",
];
const SENSITIVE: &[&str] = &[
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "authorization",
    "cookie",
    "password",
    "secret",
    "email",
    "user",
    "prompt",
    "completion",
    "content",
    "body",
    "arguments",
    "result",
    "url",
    "signed_url",
];

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum LogFormat {
    Json,
    #[default]
    Text,
}

/// Installs the global subscriber. Dependencies only reach stdout from WARNING up.
pub fn init(level: &str, format: LogFormat) -> anyhow::Result<()> {
    let level: Level = level
        .parse()
        .map_err(|_| anyhow::anyhow!("invalid log_level {level}"))?;
    let colors = std::io::stdout().is_terminal() && std::env::var_os("NO_COLOR").is_none();
    let layer = StdoutLayer::new(format, colors, std::io::stdout).with_filter(
        tracing_subscriber::filter::filter_fn(move |m| enabled(m, level)),
    );
    tracing_subscriber::registry().with(layer).try_init()?;
    Ok(())
}

fn enabled(m: &tracing::Metadata<'_>, level: Level) -> bool {
    if m.is_span() {
        return true;
    }
    if m.target() == "fred.security.audit" {
        return *m.level() <= Level::INFO;
    }
    let own = m.target().starts_with("fred_manager") || m.target() == HTTP_TARGET;
    *m.level() <= if own { level } else { Level::WARN.min(level) }
}

/// Fields recorded on a span, kept in its extensions for every event inside it.
struct SpanFields(Map<String, Value>);

struct JsonVisitor<'a>(&'a mut Map<String, Value>);

impl Visit for JsonVisitor<'_> {
    fn record_str(&mut self, field: &Field, value: &str) {
        self.0.insert(field.name().into(), value.into());
    }
    fn record_i64(&mut self, field: &Field, value: i64) {
        self.0.insert(field.name().into(), value.into());
    }
    fn record_u64(&mut self, field: &Field, value: u64) {
        self.0.insert(field.name().into(), value.into());
    }
    fn record_f64(&mut self, field: &Field, value: f64) {
        self.0.insert(field.name().into(), json!(value));
    }
    fn record_bool(&mut self, field: &Field, value: bool) {
        self.0.insert(field.name().into(), value.into());
    }
    fn record_debug(&mut self, field: &Field, value: &dyn std::fmt::Debug) {
        self.0
            .insert(field.name().into(), format!("{value:?}").into());
    }
}

pub struct StdoutLayer<W> {
    format: LogFormat,
    colors: bool,
    writer: Mutex<W>,
}

impl<W> StdoutLayer<W> {
    pub fn new<F: FnOnce() -> W>(format: LogFormat, colors: bool, writer: F) -> Self {
        Self {
            format,
            colors,
            writer: Mutex::new(writer()),
        }
    }
}

impl<S, W> Layer<S> for StdoutLayer<W>
where
    S: Subscriber + for<'a> LookupSpan<'a>,
    W: Write + Send + 'static,
{
    fn on_new_span(&self, attrs: &span::Attributes<'_>, id: &span::Id, ctx: Context<'_, S>) {
        let mut fields = Map::new();
        attrs.record(&mut JsonVisitor(&mut fields));
        if let Some(span) = ctx.span(id) {
            span.extensions_mut().insert(SpanFields(fields));
        }
    }

    fn on_record(&self, id: &span::Id, values: &span::Record<'_>, ctx: Context<'_, S>) {
        if let Some(span) = ctx.span(id)
            && let Some(fields) = span.extensions_mut().get_mut::<SpanFields>()
        {
            values.record(&mut JsonVisitor(&mut fields.0));
        }
    }

    fn on_event(&self, event: &Event<'_>, ctx: Context<'_, S>) {
        let mut context = Map::new();
        if let Some(scope) = ctx.event_scope(event) {
            for span in scope.from_root() {
                if let Some(fields) = span.extensions().get::<SpanFields>() {
                    context.extend(fields.0.clone());
                }
            }
        }
        let mut fields = Map::new();
        event.record(&mut JsonVisitor(&mut fields));
        let line = render(
            event.metadata(),
            fields,
            context,
            SystemTime::now(),
            self.format,
            self.colors,
        );
        if let Ok(mut out) = self.writer.lock() {
            let _ = writeln!(out, "{line}");
        }
    }
}

fn keep(key: &str) -> bool {
    !RESERVED.contains(&key) && !SENSITIVE.contains(&key.to_ascii_lowercase().as_str())
}

/// One output line from an event's fields and its spans' context.
fn render(
    meta: &tracing::Metadata<'_>,
    mut fields: Map<String, Value>,
    context: Map<String, Value>,
    at: SystemTime,
    format: LogFormat,
    colors: bool,
) -> String {
    let own = meta.target().starts_with("fred_manager")
        || meta.target() == HTTP_TARGET
        || meta.target() == "fred.security.audit";
    let message = match fields.remove("message") {
        _ if !own => "Dependency diagnostic".to_string(),
        Some(Value::String(m)) => m,
        Some(other) => other.to_string(),
        None => String::new(),
    };
    // Dependencies keep severity, source and context, never their own text or fields.
    let properties = if own { fields } else { Map::new() };
    let mut out: Map<String, Value> = properties.into_iter().filter(|(k, _)| keep(k)).collect();
    out.extend(context.into_iter().filter(|(k, _)| keep(k)));
    let severity = match *meta.level() {
        Level::ERROR => "ERROR",
        Level::WARN => "WARNING",
        Level::INFO => "INFO",
        _ => "DEBUG",
    };
    let since = at.duration_since(UNIX_EPOCH).unwrap_or_default();
    if format == LogFormat::Text && meta.target() != "fred.security.audit" {
        return text_line(
            since.as_secs(),
            severity,
            meta.target(),
            &message,
            &out,
            colors,
        );
    }
    out.insert("severity".into(), severity.into());
    out.insert(
        "timestamp".into(),
        json!({ "seconds": since.as_secs(), "nanos": since.subsec_nanos() }),
    );
    out.insert("message".into(), message.into());
    out.insert("logger".into(), meta.target().into());
    out.insert("service".into(), SERVICE.into());
    out.insert("category".into(), "application".into());
    out.insert(
        "logging.googleapis.com/sourceLocation".into(),
        json!({
            "file": meta.file().unwrap_or_default(),
            "line": meta.line().map(|l| l.to_string()).unwrap_or_default(),
            "function": meta.module_path().unwrap_or_default(),
        }),
    );
    out.insert("process".into(), std::process::id().into());
    out.insert(
        "thread".into(),
        std::thread::current().name().unwrap_or("unnamed").into(),
    );
    out.insert("service_role".into(), ROLE.into());
    Value::Object(out).to_string()
}

/// fred-core `TextRenderer`: no terminal-width layout, colors only on a terminal.
fn text_line(
    seconds: u64,
    severity: &str,
    logger: &str,
    message: &str,
    fields: &Map<String, Value>,
    colors: bool,
) -> String {
    let stamp = chrono::DateTime::<chrono::Utc>::from_timestamp(seconds as i64, 0)
        .map(|t| t.to_rfc3339())
        .unwrap_or_default();
    let severity = if colors {
        let color = match severity {
            "ERROR" => "31",
            "WARNING" => "33",
            _ => "36",
        };
        format!("\x1b[{color}m{severity}\x1b[0m")
    } else {
        severity.to_string()
    };
    let mut line = format!("{stamp} {severity} {SERVICE}/{logger} {message}");
    for (key, value) in fields {
        match value {
            Value::String(s) => line.push_str(&format!(" {key}={s}")),
            other => line.push_str(&format!(" {key}={other}")),
        }
    }
    line
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
        if successful {
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

/// Fred's security stream, emitted when OpenFGA acknowledges the durable write,
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
    tracing::info!(target: "fred.security.audit", audit_event = event, actor_uid = actor,
        subject = format!("user:{target}"), relation, resource, outcome = "succeeded", "[SECURITY] {event}");
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;

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

    fn capture(format: LogFormat, emit: impl FnOnce()) -> Vec<String> {
        let buffer = Buffer::default();
        let sink = buffer.clone();
        let subscriber =
            tracing_subscriber::registry().with(StdoutLayer::new(format, false, move || sink));
        tracing::subscriber::with_default(subscriber, emit);
        let text = String::from_utf8(buffer.0.lock().unwrap().clone()).unwrap();
        text.lines().map(String::from).collect()
    }

    fn json_line(emit: impl FnOnce()) -> Value {
        let lines = capture(LogFormat::Json, emit);
        assert_eq!(lines.len(), 1, "one line per event: {lines:?}");
        serde_json::from_str(&lines[0]).unwrap()
    }

    // Proves: I16
    #[test]
    fn audit_records_survive_warning_application_threshold() {
        for format in [LogFormat::Json, LogFormat::Text] {
            let buffer = Buffer::default();
            let sink = buffer.clone();
            let layer = StdoutLayer::new(format, false, move || sink).with_filter(
                tracing_subscriber::filter::filter_fn(|m| enabled(m, Level::WARN)),
            );
            let subscriber = tracing_subscriber::registry().with(layer);
            tracing::subscriber::with_default(subscriber, || {
                tracing::info!("ordinary application event");
                audit_relation(Some("actor-sub"), "target-sub", "analyst", "space:s1", true);
            });
            let output = String::from_utf8(buffer.0.lock().unwrap().clone()).unwrap();
            assert_eq!(output.lines().count(), 1);
            let line: Value = serde_json::from_str(output.trim()).unwrap();
            assert_eq!(line["logger"], "fred.security.audit");
            assert_eq!(line["audit_event"], "authz.relation.granted");
            assert_eq!(line["actor_uid"], "actor-sub");
            assert_eq!(line["subject"], "user:target-sub");
            assert_eq!(line["relation"], "analyst");
            assert_eq!(line["resource"], "space:s1");
            assert_eq!(line["outcome"], "succeeded");
        }
    }

    #[test]
    fn json_has_fred_core_fields_and_request_context() {
        let line = json_line(|| {
            let span = tracing::info_span!(
                "request",
                request_id = "r-1",
                user_id = tracing::field::Empty
            );
            let _e = span.enter();
            span.record("user_id", "bob");
            tracing::warn!(space_id = "s-1", "space created");
        });
        assert_eq!(line["severity"], "WARNING");
        assert_eq!(line["message"], "space created");
        assert_eq!(line["logger"], "fred_manager::logging::tests");
        assert_eq!(line["service"], "fred-manager");
        assert_eq!(line["service_role"], "api");
        assert_eq!(line["category"], "application");
        assert!(line["timestamp"]["seconds"].as_u64().unwrap() > 1_700_000_000);
        assert!(line["timestamp"]["nanos"].is_u64());
        assert!(line["logging.googleapis.com/sourceLocation"]["line"].is_string());
        assert_eq!(line["request_id"], "r-1");
        assert_eq!(line["user_id"], "bob");
        assert_eq!(line["space_id"], "s-1");
    }

    // Proves: I11
    #[test]
    fn sensitive_and_reserved_fields_never_leak() {
        let line = json_line(|| {
            tracing::info!(
                token = "abc",
                email = "bob@x",
                severity = "DEBUG",
                kept = 1,
                "hello"
            );
        });
        assert!(line.get("token").is_none());
        assert!(line.get("email").is_none());
        assert_eq!(line["severity"], "INFO");
        assert_eq!(line["kept"], 1);
    }

    // Proves: I11
    #[test]
    fn dependencies_get_a_fixed_message_without_their_fields() {
        let line = json_line(|| {
            tracing::warn!(target: "sqlx::query", statement = "select secret", "slow statement");
        });
        assert_eq!(line["message"], "Dependency diagnostic");
        assert_eq!(line["logger"], "sqlx::query");
        assert!(line.get("statement").is_none());
    }

    // Proves: I13
    #[tokio::test]
    async fn requests_carry_ids_and_end_with_one_http_event() {
        use axum::{Router, body::Body, routing::get};
        use tower::ServiceExt;

        let buffer = Buffer::default();
        let sink = buffer.clone();
        let subscriber = tracing_subscriber::registry().with(StdoutLayer::new(
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

    #[test]
    fn text_is_one_readable_line() {
        let lines = capture(LogFormat::Text, || {
            tracing::error!(space_id = "s-1", "failed\tthing")
        });
        assert_eq!(lines.len(), 1);
        let line = &lines[0];
        assert!(line.contains(
            " ERROR fred-manager/fred_manager::logging::tests failed\tthing space_id=s-1"
        ));
        assert!(!line.contains('\x1b'));
    }
}
