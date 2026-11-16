// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Exercise production environment configuration in separate processes, without
//! changing the test runner's environment or contacting a real collector.
use std::{
    sync::{
        Arc,
        atomic::{AtomicUsize, Ordering},
    },
    time::{Duration, Instant},
};

use axum::{Router, extract::State, http::StatusCode, routing::post};
use fred_rust_sdk::telemetry;
use tracing_subscriber::prelude::*;

#[tokio::test]
async fn disabled_and_unavailable_export_do_not_block_work_or_shutdown() {
    if let Ok(mode) = std::env::var("FRED_TELEMETRY_TEST_CHILD") {
        let provider = telemetry::provider_from_env("synthetic-rust").unwrap();
        if mode == "disabled" {
            assert!(provider.is_none());
            telemetry::shutdown(provider).await;
            return;
        }
        let provider = provider.unwrap();
        let subscriber = tracing_subscriber::registry().with(telemetry::layer(&provider));
        let _guard = tracing::subscriber::set_default(subscriber);
        let started = Instant::now();
        // More than the bounded queue, while the receiver fails or stalls.
        for _ in 0..4096 {
            let _span =
                tracing::info_span!(target: "fred.telemetry", "control_plane.http").entered();
        }
        assert!(started.elapsed() < Duration::from_secs(2));
        let shutdown_started = Instant::now();
        telemetry::shutdown(Some(provider)).await;
        assert!(shutdown_started.elapsed() < Duration::from_secs(6));
        return;
    }

    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let endpoint = format!("http://{}", listener.local_addr().unwrap());
    let requests = Arc::new(AtomicUsize::new(0));
    let received = requests.clone();
    let server = tokio::spawn(async move {
        axum::serve(
            listener,
            Router::new()
                .route(
                    "/unavailable",
                    post(|State(requests): State<Arc<AtomicUsize>>| async move {
                        requests.fetch_add(1, Ordering::Relaxed);
                        StatusCode::SERVICE_UNAVAILABLE
                    }),
                )
                .route(
                    "/stalled",
                    post(|State(requests): State<Arc<AtomicUsize>>| async move {
                        requests.fetch_add(1, Ordering::Relaxed);
                        std::future::pending::<StatusCode>().await
                    }),
                )
                .with_state(received),
        )
        .await
        .unwrap();
    });
    for mode in ["disabled", "unavailable", "stalled"] {
        let before = requests.load(Ordering::Relaxed);
        let endpoint = endpoint.clone();
        let outcome = tokio::task::spawn_blocking(move || {
            let mut command = std::process::Command::new(std::env::current_exe().unwrap());
            // Isolate configured endpoints, headers and sampling from the developer's shell.
            for (key, _) in std::env::vars_os() {
                if key.to_string_lossy().starts_with("OTEL_") {
                    command.env_remove(key);
                }
            }
            let mut child = command
                .args([
                    "--exact",
                    "disabled_and_unavailable_export_do_not_block_work_or_shutdown",
                    "--nocapture",
                ])
                .env("NO_PROXY", "*")
                .env("FRED_TELEMETRY_TEST_CHILD", mode)
                .env(
                    "FRED_OTEL_ENABLED",
                    if mode == "disabled" { "false" } else { "true" },
                )
                .env(
                    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
                    if mode == "disabled" {
                        "invalid endpoint".into()
                    } else {
                        format!("{endpoint}/{mode}")
                    },
                )
                .spawn()
                .unwrap();
            let started = Instant::now();
            loop {
                if let Some(status) = child.try_wait().unwrap() {
                    return status.success();
                }
                if started.elapsed() > Duration::from_secs(12) {
                    child.kill().unwrap();
                    child.wait().unwrap();
                    return false;
                }
                std::thread::sleep(Duration::from_millis(20));
            }
        })
        .await
        .unwrap();
        let contacted = requests.load(Ordering::Relaxed) > before;
        if !outcome || contacted != (mode != "disabled") {
            server.abort();
            let _ = server.await;
            panic!("export mode {mode} failed or exceeded the process deadline");
        }
    }
    server.abort();
    assert!(server.await.unwrap_err().is_cancelled());
}
