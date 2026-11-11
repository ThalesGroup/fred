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
//! per line or readable text, the same core fields, request context as top-level fields,
//! and dependency events reduced to a fixed diagnostic. The collector routes stdout.

use std::{
    io::{IsTerminal, Write},
    sync::Mutex,
    time::{SystemTime, UNIX_EPOCH},
};

use serde::Deserialize;
use serde_json::{Map, Value, json};
use tracing::{
    Event, Level, Subscriber,
    field::{Field, Visit},
    span,
};
use tracing_subscriber::{Layer, layer::Context, prelude::*, registry::LookupSpan};

/// The logger of the request completion event, as fred-core's `http` logger.
pub const HTTP_TARGET: &str = "http";
/// The security/audit logger, always JSON and always from INFO.
pub const AUDIT_TARGET: &str = "fred.security.audit";

/// Who writes a line: on every event, whatever the process does.
#[derive(Clone, Copy)]
pub struct LogIdentity {
    pub service: &'static str,
    /// `api`, `worker`, `migration` or `job`.
    pub role: &'static str,
    /// The crate whose events keep their text; other crates are dependencies.
    pub owner: &'static str,
}

impl LogIdentity {
    fn owns(self, target: &str) -> bool {
        target.starts_with(self.owner)
            || target.starts_with("fred_")
            || target == HTTP_TARGET
            || target == AUDIT_TARGET
    }
}

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

/// An error chain for the `error` field: `Display`, because SQL `Debug` prints the
/// database's DETAIL with row values, and without the query string of a failed call.
pub fn error_chain(error: &anyhow::Error) -> String {
    let mut text = format!("{error:#}");
    for cause in error.chain() {
        if let Some(url) = cause
            .downcast_ref::<reqwest::Error>()
            .and_then(reqwest::Error::url)
        {
            text = text.replace(url.as_str(), url.path());
        }
    }
    text
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Deserialize, utoipa::ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum LogFormat {
    Json,
    #[default]
    Text,
}

/// Installs the global subscriber. Dependencies only reach stdout from WARNING up.
pub fn init(identity: LogIdentity, level: &str, format: LogFormat) -> anyhow::Result<()> {
    let level: Level = level
        .parse()
        .map_err(|_| anyhow::anyhow!("invalid log_level {level}"))?;
    let colors = std::io::stdout().is_terminal() && std::env::var_os("NO_COLOR").is_none();
    // One output stream needs a global filter. A per-layer filter can retain a
    // disabled dependency `enabled!` probe and suppress the following cached event.
    tracing_subscriber::registry()
        .with(tracing_subscriber::filter::filter_fn(move |m| {
            enabled(m, level, identity)
        }))
        .with(StdoutLayer::new(identity, format, colors, std::io::stdout))
        .try_init()?;
    Ok(())
}

fn enabled(m: &tracing::Metadata<'_>, level: Level, identity: LogIdentity) -> bool {
    if m.target().starts_with("rmcp") {
        return false; // MCP diagnostics are reduced to stable codes at the discovery boundary.
    }
    if m.is_span() {
        return true;
    }
    if m.target() == AUDIT_TARGET {
        return *m.level() <= Level::INFO;
    }
    let own = identity.owns(m.target());
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
    identity: LogIdentity,
    format: LogFormat,
    colors: bool,
    writer: Mutex<W>,
}

impl<W> StdoutLayer<W> {
    pub fn new<F: FnOnce() -> W>(
        identity: LogIdentity,
        format: LogFormat,
        colors: bool,
        writer: F,
    ) -> Self {
        Self {
            identity,
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
            self.identity,
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
    identity: LogIdentity,
    meta: &tracing::Metadata<'_>,
    mut fields: Map<String, Value>,
    context: Map<String, Value>,
    at: SystemTime,
    format: LogFormat,
    colors: bool,
) -> String {
    let own = identity.owns(meta.target());
    let message = match fields.remove("message") {
        _ if !own => "Dependency diagnostic".to_string(),
        Some(Value::String(m)) => m,
        Some(other) => other.to_string(),
        None => String::new(),
    };
    // Dependencies keep severity, source, context and their numeric or boolean fields
    // (such as a slow acquire's `elapsed_secs`), never their own text or text fields.
    let properties = if own {
        fields
    } else {
        fields
            .into_iter()
            .filter(|(_, value)| value.is_number() || value.is_boolean())
            .collect()
    };
    let mut out: Map<String, Value> = properties.into_iter().filter(|(k, _)| keep(k)).collect();
    out.extend(context.into_iter().filter(|(k, _)| keep(k)));
    let severity = match *meta.level() {
        Level::ERROR => "ERROR",
        Level::WARN => "WARNING",
        Level::INFO => "INFO",
        _ => "DEBUG",
    };
    let since = at.duration_since(UNIX_EPOCH).unwrap_or_default();
    if format == LogFormat::Text && meta.target() != AUDIT_TARGET {
        return text_line(
            identity,
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
    out.insert("service".into(), identity.service.into());
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
    out.insert("service_role".into(), identity.role.into());
    Value::Object(out).to_string()
}

/// fred-core `TextRenderer`: no terminal-width layout, colors only on a terminal.
fn text_line(
    identity: LogIdentity,
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
    let LogIdentity { service, role, .. } = identity;
    let mut line = format!("{stamp} {severity} {service}/{role}/{logger} {message}");
    for (key, value) in fields {
        match value {
            Value::String(s) => line.push_str(&format!(" {key}={s}")),
            other => line.push_str(&format!(" {key}={other}")),
        }
    }
    line
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;

    const IDENTITY: LogIdentity = LogIdentity {
        service: "control-plane",
        role: "api",
        owner: "fred_rust_sdk",
    };

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

    fn capture_as(identity: LogIdentity, format: LogFormat, emit: impl FnOnce()) -> Vec<String> {
        let buffer = Buffer::default();
        let sink = buffer.clone();
        let subscriber = tracing_subscriber::registry().with(StdoutLayer::new(
            identity,
            format,
            false,
            move || sink,
        ));
        tracing::subscriber::with_default(subscriber, emit);
        let text = String::from_utf8(buffer.0.lock().unwrap().clone()).unwrap();
        text.lines().map(String::from).collect()
    }

    fn capture(format: LogFormat, emit: impl FnOnce()) -> Vec<String> {
        capture_as(IDENTITY, format, emit)
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
            let subscriber = tracing_subscriber::registry()
                .with(tracing_subscriber::filter::filter_fn(|m| {
                    enabled(m, Level::WARN, IDENTITY)
                }))
                .with(StdoutLayer::new(IDENTITY, format, false, move || sink));
            tracing::subscriber::with_default(subscriber, || {
                tracing::info!("ordinary application event");
                tracing::info!(target: AUDIT_TARGET, audit_event = "authz.relation.granted", "[SECURITY] event");
            });
            let output = String::from_utf8(buffer.0.lock().unwrap().clone()).unwrap();
            assert_eq!(output.lines().count(), 1);
            let line: Value = serde_json::from_str(output.trim()).unwrap();
            assert_eq!(line["logger"], AUDIT_TARGET);
            assert_eq!(line["audit_event"], "authz.relation.granted");
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
        assert_eq!(line["logger"], "fred_rust_sdk::logging::tests");
        assert_eq!(line["service"], "control-plane");
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
    fn dependencies_get_a_fixed_message_and_only_numeric_fields() {
        let line = json_line(|| {
            tracing::warn!(target: "sqlx::query", statement = "select secret", error = ?"secret", elapsed_secs = 3.5, rows_affected = 2_u64, "slow statement");
        });
        assert_eq!(line["message"], "Dependency diagnostic");
        assert_eq!(line["logger"], "sqlx::query");
        assert!(line.get("statement").is_none());
        assert!(line.get("error").is_none());
        // A bounded cause stays diagnosable.
        assert_eq!(line["elapsed_secs"], 3.5);
        assert_eq!(line["rows_affected"], 2);
    }

    #[test]
    fn text_is_one_readable_line() {
        let lines = capture(LogFormat::Text, || {
            tracing::error!(space_id = "s-1", "failed\tthing")
        });
        assert_eq!(lines.len(), 1);
        let line = &lines[0];
        assert!(line.contains(
            " ERROR control-plane/api/fred_rust_sdk::logging::tests failed\tthing space_id=s-1"
        ));
        assert!(!line.contains('\x1b'));
    }

    #[tokio::test]
    async fn error_chain_drops_the_query_string_of_a_failed_call() {
        let failure = reqwest::Client::new()
            .get("http://127.0.0.1:1/users?email=SENTINEL")
            .send()
            .await
            .unwrap_err();
        let text = error_chain(&anyhow::Error::new(failure).context("directory lookup"));
        assert!(text.contains("directory lookup"), "{text}");
        assert!(text.contains("/users"), "{text}");
        assert!(!text.contains("SENTINEL"), "{text}");
    }

    /// The same event and rules as fred-core's `test_log_contract.py`.
    #[test]
    fn output_matches_the_shared_contract() {
        const CONTRACT: &str =
            include_str!("../../fred-core/fred_core/tests/logs/log_contract.json");
        let contract: Value = serde_json::from_str(CONTRACT).unwrap();
        let names = |key: &str| -> Vec<String> {
            let mut names: Vec<String> = contract[key]
                .as_array()
                .unwrap()
                .iter()
                .map(|name| name.as_str().unwrap().to_owned())
                .collect();
            names.sort();
            names
        };
        let sorted = |list: &[&str]| {
            let mut list: Vec<String> = list.iter().map(|name| (*name).to_owned()).collect();
            list.sort();
            list
        };
        assert_eq!(sorted(RESERVED), names("reserved_fields"));
        assert_eq!(sorted(SENSITIVE), names("sensitive_fields"));

        let identity = LogIdentity {
            service: "contract-service",
            role: "api",
            owner: "contract",
        };
        let emit = || {
            let span = tracing::info_span!("request", correlation_id = "correlation-1");
            let _entered = span.enter();
            tracing::warn!(
                target: "contract.event",
                operation_id = "operation-1",
                error_code = "contract_failed",
                attempt = 3,
                done = false,
                token = "SENTINEL",
                email = "SENTINEL",
                severity = "SENTINEL",
                "Contract event"
            );
        };
        let [line] = capture_as(identity, LogFormat::Json, emit)
            .try_into()
            .unwrap();
        println!("{line}");
        let mut event: Map<String, Value> = serde_json::from_str(&line).unwrap();
        let stamp = event.remove("timestamp").unwrap();
        assert!(stamp["seconds"].is_u64() && stamp["nanos"].is_u64());
        let source = event
            .remove("logging.googleapis.com/sourceLocation")
            .unwrap();
        assert!(source["file"].is_string() && source["line"].is_string());
        assert!(source["function"].is_string());
        assert!(event.remove("process").unwrap().is_u64());
        assert!(event.remove("thread").unwrap().is_string());
        assert_eq!(Value::Object(event), contract["event"]);

        let [text] = capture_as(identity, LogFormat::Text, emit)
            .try_into()
            .unwrap();
        let (_, line) = text.split_once(' ').unwrap();
        let expected = contract["text"]["line"].as_str().unwrap();
        let detail = line.strip_prefix(expected).unwrap();
        let mut detail: Vec<&str> = detail.split_whitespace().collect();
        detail.sort_unstable();
        let fields: Vec<&str> = contract["text"]["fields"]
            .as_array()
            .unwrap()
            .iter()
            .map(|field| field.as_str().unwrap())
            .collect();
        assert_eq!(detail, fields);
    }
}
