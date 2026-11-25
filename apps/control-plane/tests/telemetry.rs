// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Offline HTTP requests through the production middleware and safe export layer.
use axum::{Router, body::Body, http::Request, routing::get};
use fred_rust_sdk::telemetry;
use opentelemetry::{KeyValue, trace::Status};
use opentelemetry_sdk::trace::{InMemorySpanExporter, SdkTracerProvider, SimpleSpanProcessor};
use tower::ServiceExt;
use tracing::Instrument;
use tracing_subscriber::prelude::*;

fn request(parent: &str) -> Request<Body> {
    Request::builder()
        .uri("/")
        .header("traceparent", parent)
        .body(Body::empty())
        .unwrap()
}

#[tokio::test]
async fn concurrent_requests_keep_w3c_parents_and_invalid_context_starts_fresh() {
    let exporter = InMemorySpanExporter::default();
    let provider = SdkTracerProvider::builder()
        .with_span_processor(telemetry::SafeSpans(SimpleSpanProcessor::new(
            exporter.clone(),
        )))
        .build();
    let subscriber = tracing_subscriber::registry().with(telemetry::layer(&provider));
    let _guard = tracing::subscriber::set_default(subscriber);
    let app = Router::new()
        .route(
            "/",
            get(|| async {
                async {
                    tokio::task::yield_now().await;
                    "ok"
                }
                .instrument(tracing::info_span!(target: "fred.telemetry", "auth.jwt.validate"))
                .await
            }),
        )
        .layer(axum::middleware::from_fn(
            control_plane::logging::request_logging,
        ));
    let (first, second) = tokio::join!(
        app.clone().oneshot(request(
            "00-11111111111111111111111111111111-aaaaaaaaaaaaaaaa-01"
        )),
        app.clone().oneshot(request(
            "00-22222222222222222222222222222222-bbbbbbbbbbbbbbbb-01"
        )),
    );
    assert!(first.unwrap().headers().contains_key("x-request-id"));
    assert!(second.unwrap().headers().contains_key("x-correlation-id"));
    app.oneshot(request(
        "00-00000000000000000000000000000000-aaaaaaaaaaaaaaaa-01",
    ))
    .await
    .unwrap();
    let spans = exporter.get_finished_spans().unwrap();
    assert_eq!(spans.len(), 6);
    for (trace, parent) in [
        ("11111111111111111111111111111111", "aaaaaaaaaaaaaaaa"),
        ("22222222222222222222222222222222", "bbbbbbbbbbbbbbbb"),
    ] {
        let server = spans
            .iter()
            .find(|s| {
                s.name == "control_plane.http" && s.span_context.trace_id().to_string() == trace
            })
            .unwrap();
        assert_eq!(server.parent_span_id.to_string(), parent);
        assert_eq!(server.status, Status::Unset);
        assert!(server.parent_span_is_remote);
        let child = spans
            .iter()
            .find(|s| {
                s.name == "auth.jwt.validate" && s.span_context.trace_id().to_string() == trace
            })
            .unwrap();
        assert_eq!(child.parent_span_id, server.span_context.span_id());
        assert!(
            server
                .attributes
                .contains(&KeyValue::new("http.response.status_code", 200_i64))
        );
    }
    let fresh = spans
        .iter()
        .find(|s| s.name == "control_plane.http" && !s.parent_span_is_remote)
        .unwrap();
    assert_eq!(fresh.parent_span_id, opentelemetry::trace::SpanId::INVALID);
    assert!(fresh.span_context.is_valid());
}

#[tokio::test]
async fn cancelling_request_closes_server_span() {
    let exporter = InMemorySpanExporter::default();
    let provider = SdkTracerProvider::builder()
        .with_span_processor(telemetry::SafeSpans(SimpleSpanProcessor::new(
            exporter.clone(),
        )))
        .build();
    let subscriber = tracing_subscriber::registry().with(telemetry::layer(&provider));
    let _guard = tracing::subscriber::set_default(subscriber);
    let app = Router::new()
        .route("/", get(std::future::pending::<&'static str>))
        .layer(axum::middleware::from_fn(
            control_plane::logging::request_logging,
        ));
    let future = app.oneshot(request(
        "00-11111111111111111111111111111111-aaaaaaaaaaaaaaaa-01",
    ));
    assert!(
        tokio::time::timeout(std::time::Duration::from_millis(5), future)
            .await
            .is_err()
    );
    let spans = exporter.get_finished_spans().unwrap();
    assert_eq!(spans.len(), 1);
    assert_eq!(spans[0].status, Status::error(""));
    assert!(
        spans[0]
            .attributes
            .contains(&KeyValue::new("fred.outcome", "cancelled"))
    );
    assert!(spans[0].end_time >= spans[0].start_time);
}

#[tokio::test]
async fn server_failure_exports_error_status_without_response_details() {
    let exporter = InMemorySpanExporter::default();
    let provider = SdkTracerProvider::builder()
        .with_span_processor(telemetry::SafeSpans(SimpleSpanProcessor::new(
            exporter.clone(),
        )))
        .build();
    let subscriber = tracing_subscriber::registry().with(telemetry::layer(&provider));
    let _guard = tracing::subscriber::set_default(subscriber);
    let app = Router::new()
        .route(
            "/",
            get(|| async {
                (
                    axum::http::StatusCode::INTERNAL_SERVER_ERROR,
                    "private-error-details",
                )
            }),
        )
        .layer(axum::middleware::from_fn(
            control_plane::logging::request_logging,
        ));
    let response = app
        .oneshot(request(
            "00-11111111111111111111111111111111-aaaaaaaaaaaaaaaa-01",
        ))
        .await
        .unwrap();
    assert_eq!(
        response.status(),
        axum::http::StatusCode::INTERNAL_SERVER_ERROR
    );
    let spans = exporter.get_finished_spans().unwrap();
    assert_eq!(spans.len(), 1);
    assert_eq!(spans[0].status, Status::error(""));
    assert!(
        spans[0]
            .attributes
            .contains(&KeyValue::new("http.response.status_code", 500_i64))
    );
    assert!(!format!("{spans:?}").contains("private-error-details"));
}
