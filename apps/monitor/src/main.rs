// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

mod api;
mod config;
mod kubernetes;

use std::{sync::Arc, time::Duration};

use anyhow::Result;
use fred_rust_sdk::{
    logging::{self, LogFormat, LogIdentity},
    security::authentication::Authenticator,
};
use sqlx::postgres::PgPoolOptions;

#[tokio::main]
async fn main() -> Result<()> {
    if std::env::args().nth(1).as_deref() == Some("generate-openapi") {
        println!("{}", serde_json::to_string_pretty(&api::openapi())?);
        return Ok(());
    }
    logging::init(
        LogIdentity {
            service: "monitor",
            role: "api",
            owner: "monitor",
        },
        &std::env::var("MONITOR_LOG_LEVEL").unwrap_or_else(|_| "info".into()),
        match std::env::var("MONITOR_LOG_FORMAT").as_deref() {
            Ok("json") => LogFormat::Json,
            _ => LogFormat::Text,
        },
    )?;
    // Once logging runs, a fatal error is one more structured event, not stray stderr.
    if let Err(error) = serve().await {
        tracing::error!(error = logging::error_chain(&error), "monitor stopped");
        std::process::exit(1);
    }
    Ok(())
}

async fn serve() -> Result<()> {
    let config = config::Config::from_env()?;
    let client = kube::Client::try_default().await?;
    let namespace = config
        .namespace
        .unwrap_or_else(|| client.default_namespace().to_owned());
    let state = api::AppState {
        kubernetes: kubernetes::Kubernetes::new(client, namespace),
        auth: Arc::new(Authenticator::start(config.security).await?),
        // PostgreSQL failure must not kill the process; protected requests fail closed.
        pool: PgPoolOptions::new()
            .max_connections(2)
            .acquire_timeout(Duration::from_secs(2))
            .connect_lazy(&config.database_url)?,
    };
    let listener = tokio::net::TcpListener::bind(config.bind).await?;
    tracing::info!(address = %listener.local_addr()?, "monitor listening");
    axum::serve(listener, api::router(state))
        .with_graceful_shutdown(shutdown())
        .await?;
    Ok(())
}

async fn shutdown() {
    #[cfg(unix)]
    {
        match tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate()) {
            Ok(mut terminate) => {
                tokio::select! {
                    result = tokio::signal::ctrl_c() => {
                        if let Err(error) = result {
                            tracing::error!(%error, "interrupt handler failed");
                        }
                    }
                    _ = terminate.recv() => {}
                }
            }
            Err(error) => tracing::error!(%error, "termination handler failed"),
        }
    }
    #[cfg(not(unix))]
    if let Err(error) = tokio::signal::ctrl_c().await {
        tracing::error!(%error, "interrupt handler failed");
    }
}
