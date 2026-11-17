// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Opt-in technical spans on the existing tracing subscriber. No logs or payloads
//! are exported: the processor admits a closed vocabulary before the batch queue.

use std::time::Duration;

use axum::http::HeaderMap;
use opentelemetry::{
    Context, KeyValue, Value,
    propagation::{Extractor, Injector, TextMapPropagator},
    trace::{Status, TracerProvider},
};
use opentelemetry_otlp::{Protocol, WithExportConfig};
use opentelemetry_sdk::{
    Resource,
    error::OTelSdkResult,
    propagation::TraceContextPropagator,
    trace::{
        BatchConfigBuilder, BatchSpanProcessor, Sampler, SdkTracerProvider, Span, SpanData,
        SpanProcessor,
    },
};
use tracing_opentelemetry::OpenTelemetrySpanExt;
use tracing_subscriber::{Layer, registry::LookupSpan};

/// Developer-only diagnostics configured alongside the application's other YAML settings.
#[derive(Debug, Clone, Default, serde::Deserialize, utoipa::ToSchema)]
#[serde(tag = "tracer", rename_all = "lowercase", deny_unknown_fields)]
pub enum ObservabilityConfig {
    #[default]
    Logging,
    Null,
    Diagnostic {
        diagnostic: DiagnosticConfig,
    },
}

impl ObservabilityConfig {
    pub fn diagnostic(&self) -> Option<&DiagnosticConfig> {
        match self {
            Self::Diagnostic { diagnostic } => Some(diagnostic),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, serde::Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct DiagnosticConfig {
    pub collector_endpoint: String,
}

impl DiagnosticConfig {
    pub fn validate(&self) -> anyhow::Result<()> {
        let url = reqwest::Url::parse(&self.collector_endpoint)?;
        anyhow::ensure!(
            matches!(url.scheme(), "http" | "https") && url.host_str().is_some(),
            "diagnostic.collector_endpoint must be an HTTP(S) URL"
        );
        Ok(())
    }
}

/// No exporter, worker or network activity without a configured diagnostic backend.
pub fn provider_from_config(
    service: &'static str,
    config: Option<&DiagnosticConfig>,
) -> anyhow::Result<Option<SdkTracerProvider>> {
    let Some(config) = config else {
        return Ok(None);
    };
    config.validate()?;
    let exporter = opentelemetry_otlp::SpanExporter::builder()
        .with_http()
        .with_endpoint(&config.collector_endpoint)
        .with_protocol(Protocol::HttpBinary)
        .with_timeout(Duration::from_secs(3))
        .build()?;
    let processor = BatchSpanProcessor::builder(exporter)
        .with_batch_config(
            BatchConfigBuilder::default()
                .with_max_queue_size(2048)
                .with_max_export_batch_size(256)
                .with_scheduled_delay(Duration::from_secs(1))
                .build(),
        )
        .build();
    Ok(Some(
        SdkTracerProvider::builder()
            .with_sampler(Sampler::ParentBased(Box::new(Sampler::AlwaysOff)))
            .with_span_processor(SafeSpans(processor))
            .with_resource(Resource::builder_empty().with_service_name(service).build())
            .build(),
    ))
}

/// Drains the bounded batch queue away from Tokio's request workers.
pub async fn shutdown(provider: Option<SdkTracerProvider>) {
    if let Some(provider) = provider {
        let result = tokio::task::spawn_blocking(move || {
            provider.shutdown_with_timeout(Duration::from_secs(5))
        })
        .await;
        if !matches!(result, Ok(Ok(()))) {
            tracing::warn!("Technical tracing shutdown did not finish successfully");
        }
    }
}

/// Only explicitly named Fred spans reach OTel; ordinary tracing events stay stdout-only.
pub fn layer<S>(provider: &SdkTracerProvider) -> impl Layer<S>
where
    S: tracing::Subscriber + for<'a> LookupSpan<'a>,
{
    tracing_opentelemetry::layer()
        .with_tracer(provider.tracer("fred-rust-sdk"))
        .with_location(false)
        .with_threads(false)
        .with_level(false)
        .with_target(false)
        .with_tracked_inactivity(false)
        .with_error_events_to_status(false)
        .with_error_events_to_exceptions(false)
        .with_error_fields_to_exceptions(false)
        .with_error_records_to_exceptions(false)
        .with_filter(tracing_subscriber::filter::filter_fn(|metadata| {
            metadata.is_span() && metadata.target() == "fred.telemetry"
        }))
}

struct Headers<'a>(&'a HeaderMap);
impl Extractor for Headers<'_> {
    fn get(&self, key: &str) -> Option<&str> {
        self.0.get(key)?.to_str().ok()
    }
    fn keys(&self) -> Vec<&str> {
        self.0.keys().map(|key| key.as_str()).collect()
    }
}

/// Missing/invalid headers start a new trace, never inherit another request's context.
pub fn set_remote_parent(span: &tracing::Span, headers: &HeaderMap) {
    let parent =
        TraceContextPropagator::new().extract_with_context(&Context::new(), &Headers(headers));
    let _ = span.set_parent(parent);
}

/// Inject only W3C trace context, never baggage or credentials.
pub fn inject(request: reqwest::RequestBuilder) -> reqwest::RequestBuilder {
    struct Outgoing(HeaderMap);
    impl Injector for Outgoing {
        fn set(&mut self, key: &str, value: String) {
            if let (Ok(key), Ok(value)) = (key.parse::<axum::http::HeaderName>(), value.parse()) {
                self.0.insert(key, value);
            }
        }
    }
    let mut headers = Outgoing(HeaderMap::new());
    TraceContextPropagator::new().inject_context(&tracing::Span::current().context(), &mut headers);
    request.headers(headers.0)
}

/// Defense at the export boundary: neither a new tracing field, event, link, nor
/// an error description can silently expose application data to the collector.
#[derive(Debug)]
pub struct SafeSpans<P>(pub P);

impl<P: SpanProcessor> SpanProcessor for SafeSpans<P> {
    fn on_start(&self, span: &mut Span, context: &Context) {
        self.0.on_start(span, context);
    }
    fn on_end(&self, mut span: SpanData) {
        let category =
            match span.name.as_ref() {
                "control_plane.http" | "control_plane.resolve_runtime" => "control_plane",
                "auth.jwt.validate" | "auth.jwks.lookup" => "auth",
                "auth.jwks.fetch" => {
                    if span.attributes.iter().any(|kv| {
                        kv.key.as_str() == "peer.service" && kv.value.as_str() == "keycloak"
                    }) {
                        "keycloak"
                    } else {
                        "auth"
                    }
                }
                _ => return,
            };
        span.attributes
            .retain(|kv| match (kv.key.as_str(), &kv.value) {
                ("peer.service", Value::String(value)) => {
                    matches!(value.as_str(), "keycloak" | "identity-provider")
                }
                ("http.request.method", Value::String(value)) => matches!(
                    value.as_str(),
                    "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "OPTIONS" | "HEAD"
                ),
                ("http.response.status_code", Value::I64(value)) => (100..=599).contains(value),
                ("fred.outcome", Value::String(value)) => {
                    matches!(value.as_str(), "responded" | "cancelled")
                }
                ("fred.cache", Value::String(value)) => {
                    matches!(value.as_str(), "hit" | "miss" | "stale" | "refreshed")
                }
                _ => false,
            });
        span.attributes
            .push(KeyValue::new("fred.category", category));
        span.attributes
            .push(KeyValue::new("fred.operation", span.name.to_string()));
        span.events = Default::default();
        span.links = Default::default();
        if matches!(span.status, Status::Error { .. }) {
            span.status = Status::error("");
        }
        self.0.on_end(span);
    }
    fn force_flush(&self) -> OTelSdkResult {
        self.0.force_flush()
    }
    fn shutdown_with_timeout(&self, timeout: Duration) -> OTelSdkResult {
        self.0.shutdown_with_timeout(timeout)
    }
    fn set_resource(&mut self, resource: &Resource) {
        self.0.set_resource(resource);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use opentelemetry::trace::{Span as _, TraceContextExt, Tracer};
    use opentelemetry_sdk::trace::{InMemorySpanExporter, SimpleSpanProcessor};
    use tracing_subscriber::prelude::*;

    #[test]
    fn technical_export_is_a_closed_vocabulary_not_a_log_export() {
        let exporter = InMemorySpanExporter::default();
        let provider = SdkTracerProvider::builder()
            .with_span_processor(SafeSpans(SimpleSpanProcessor::new(exporter.clone())))
            .build();
        let subscriber = tracing_subscriber::registry().with(layer(&provider));
        tracing::subscriber::with_default(subscriber, || {
            let span = tracing::info_span!(target: "fred.telemetry", "control_plane.http",
                token = "private-token", prompt = "private-prompt", url = "private-url",
                fred.category = "private-category", peer.service = "private-service",
                http.request.method = "POST", http.response.status_code = 200_i64);
            let _guard = span.enter();
            tracing::error!("private-event");
            let _dependency =
                tracing::info_span!(target: "sqlx", "private-query", statement = "private-sql")
                    .entered();
            let _unknown =
                tracing::info_span!(target: "fred.telemetry", "private-span-name").entered();
        });
        provider.force_flush().unwrap();
        let spans = exporter.get_finished_spans().unwrap();
        assert_eq!(spans.len(), 1);
        assert!(spans[0].events.is_empty());
        assert_eq!(spans[0].attributes.len(), 4);
        assert!(
            spans[0]
                .attributes
                .contains(&KeyValue::new("fred.category", "control_plane"))
        );
        assert!(!format!("{spans:?}").contains("private-"));
    }

    #[test]
    fn sampling_and_tracestate_follow_the_remote_parent() {
        let exporter = InMemorySpanExporter::default();
        let provider = SdkTracerProvider::builder()
            .with_span_processor(SafeSpans(SimpleSpanProcessor::new(exporter.clone())))
            .build();
        let subscriber = tracing_subscriber::registry().with(layer(&provider));
        tracing::subscriber::with_default(subscriber, || {
            for sampled in ["00", "01"] {
                let incoming =
                    format!("00-11111111111111111111111111111111-aaaaaaaaaaaaaaaa-{sampled}");
                let mut headers = HeaderMap::new();
                headers.insert("traceparent", incoming.parse().unwrap());
                headers.insert("tracestate", "vendor=synthetic".parse().unwrap());
                headers.insert("baggage", "private=value".parse().unwrap());
                let server = tracing::info_span!(target: "fred.telemetry", "control_plane.http");
                set_remote_parent(&server, &headers);
                let _server = server.enter();
                let child = tracing::info_span!(target: "fred.telemetry", "auth.jwks.fetch");
                let _child = child.enter();
                let outgoing = inject(reqwest::Client::new().get("http://unused"))
                    .build()
                    .unwrap();
                let expected = format!(
                    "00-11111111111111111111111111111111-{}-{sampled}",
                    child.context().span().span_context().span_id()
                );
                assert_eq!(outgoing.headers()["traceparent"], expected);
                assert_eq!(outgoing.headers()["tracestate"], "vendor=synthetic");
                assert!(!outgoing.headers().contains_key("baggage"));
            }
        });
        let spans = exporter.get_finished_spans().unwrap();
        assert_eq!(
            spans.len(),
            2,
            "unsampled traces must propagate without export"
        );
        let server = spans
            .iter()
            .find(|s| s.name == "control_plane.http")
            .unwrap();
        let child = spans.iter().find(|s| s.name == "auth.jwks.fetch").unwrap();
        assert_eq!(server.parent_span_id.to_string(), "aaaaaaaaaaaaaaaa");
        assert_eq!(child.parent_span_id, server.span_context.span_id());
        assert!(spans.iter().all(|s| s.span_context.is_sampled()));
    }

    #[test]
    fn processor_also_removes_direct_otel_events_and_error_descriptions() {
        let exporter = InMemorySpanExporter::default();
        let provider = SdkTracerProvider::builder()
            .with_span_processor(SafeSpans(SimpleSpanProcessor::new(exporter.clone())))
            .build();
        let mut span = provider.tracer("test").start("auth.jwt.validate");
        span.set_attribute(KeyValue::new("secret", "private-attribute"));
        span.add_event("private-event", vec![]);
        span.set_status(Status::error("private-error"));
        span.end();
        let spans = exporter.get_finished_spans().unwrap();
        assert_eq!(spans.len(), 1);
        assert!(!format!("{spans:?}").contains("private-"));
        assert!(matches!(spans[0].status, Status::Error { .. }));
    }
}
