// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Prometheus series with the names, millisecond buckets and labels of fred-core's
//! KPI exporter (`prometheus_kpi_store.py`), so the Python dashboards read Rust
//! services unchanged. Labels hold closed sets, model identifiers or route templates,
//! never a person, space, session or conversation.

use std::{sync::LazyLock, time::Duration};

use axum::{
    Router,
    http::{StatusCode, header},
    response::{IntoResponse, Response},
    routing::get,
};
use prometheus::{HistogramOpts, HistogramVec, Registry, TextEncoder};

/// fred-core's `MS_BUCKETS`: keep both lists equal.
const MS_BUCKETS: [f64; 16] = [
    5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 1500.0, 2000.0, 2500.0, 5000.0, 10000.0,
    30000.0, 60000.0, 120000.0,
];

struct Series {
    registry: Registry,
    requests: HistogramVec,
    model_calls: HistogramVec,
    turns: HistogramVec,
}

static SERIES: LazyLock<Result<Series, prometheus::Error>> = LazyLock::new(|| {
    let registry = Registry::new();
    let histogram = |name: &str, labels: &[&str]| {
        let opts = HistogramOpts::new(name, "KPI timer").buckets(MS_BUCKETS.to_vec());
        let series = HistogramVec::new(opts, labels)?;
        registry.register(Box::new(series.clone()))?;
        Ok::<_, prometheus::Error>(series)
    };
    let requests = histogram(
        "api_request_latency_ms",
        &["service", "route", "method", "http_status", "status"],
    )?;
    let model_calls = histogram("llm_call_latency_ms", &["service", "model_name", "status"])?;
    let turns = histogram(
        "agent_turn_completed",
        &[
            "service",
            "runtime_id",
            "template_agent_id",
            "model_name",
            "finish_reason",
        ],
    )?;
    Ok(Series {
        registry,
        requests,
        model_calls,
        turns,
    })
});

fn observe(pick: fn(&Series) -> &HistogramVec, labels: &[&str], elapsed: Duration) {
    if let Ok(series) = &*SERIES
        && let Ok(histogram) = pick(series).get_metric_with_label_values(labels)
    {
        histogram.observe(elapsed.as_secs_f64() * 1000.0);
    }
}

/// One HTTP response under its route template, until its head is ready (a stream's
/// body is not included). `status` is `ok` below 400, as in fred-core.
pub fn http_request(service: &str, route: &str, method: &str, http_status: u16, elapsed: Duration) {
    let status = if http_status < 400 { "ok" } else { "error" };
    let http_status = http_status.to_string();
    observe(
        |s| &s.requests,
        &[service, route, method, &http_status, status],
        elapsed,
    );
}

/// One completed or failed model call.
pub fn model_call(service: &str, model_name: &str, ok: bool, elapsed: Duration) {
    let status = if ok { "ok" } else { "error" };
    observe(|s| &s.model_calls, &[service, model_name, status], elapsed);
}

/// One turn that ended with `final` (its finish reason) or `execution_error` (`error`).
pub fn turn(
    service: &str,
    runtime_id: &str,
    template_agent_id: &str,
    model_name: &str,
    finish_reason: &str,
    elapsed: Duration,
) {
    observe(
        |s| &s.turns,
        &[
            service,
            runtime_id,
            template_agent_id,
            model_name,
            finish_reason,
        ],
        elapsed,
    );
}

/// `GET /metrics` for a dedicated listener: no base URL, authentication or ingress.
pub fn router() -> Router {
    Router::new().route("/metrics", get(scrape))
}

/// The text exposition format; `None` if the series could not be built or encoded.
pub fn render() -> Option<String> {
    let series = SERIES.as_ref().ok()?;
    TextEncoder::new()
        .encode_to_string(&series.registry.gather())
        .ok()
}

async fn scrape() -> Response {
    match render() {
        Some(text) => ([(header::CONTENT_TYPE, prometheus::TEXT_FORMAT)], text).into_response(),
        None => StatusCode::INTERNAL_SERVER_ERROR.into_response(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::to_bytes;

    #[tokio::test]
    async fn the_scrape_shows_python_names_labels_and_buckets() {
        http_request(
            "control-plane",
            "/spaces/{id}",
            "GET",
            404,
            Duration::from_millis(3),
        );
        model_call("control-plane", "model", true, Duration::from_millis(700));
        turn(
            "control-plane",
            "control-plane",
            "fred.github.ralph",
            "model",
            "stop",
            Duration::from_millis(1200),
        );
        let response = scrape().await;
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response.headers()[header::CONTENT_TYPE],
            prometheus::TEXT_FORMAT
        );
        let text = String::from_utf8(
            to_bytes(response.into_body(), usize::MAX)
                .await
                .unwrap()
                .to_vec(),
        )
        .unwrap();
        for line in [
            r#"api_request_latency_ms_count{http_status="404",method="GET",route="/spaces/{id}",service="control-plane",status="error"} 1"#,
            r#"llm_call_latency_ms_bucket{model_name="model",service="control-plane",status="ok",le="1000"} 1"#,
            r#"agent_turn_completed_bucket{finish_reason="stop",model_name="model",runtime_id="control-plane",service="control-plane",template_agent_id="fred.github.ralph",le="1000"} 0"#,
            r#"agent_turn_completed_sum{finish_reason="stop",model_name="model",runtime_id="control-plane",service="control-plane",template_agent_id="fred.github.ralph"} 1200"#,
        ] {
            assert!(text.contains(line), "{line} missing from:\n{text}");
        }
    }
}
