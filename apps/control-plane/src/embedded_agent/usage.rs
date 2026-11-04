// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! The bounded accounting write of one embedded turn or title.

use fred_rust_agent::Usage;
use fred_rust_sdk::inference::ModelOfferKey;
use sqlx::PgPool;
use tracing::{Instrument, Span};
use uuid::Uuid;

use crate::sessions::{ModelUsage, UsageProvenance, UsageReport, persist_usage};

pub(super) fn report(
    pool: PgPool,
    span: Span,
    provenance: UsageProvenance,
    offer: ModelOfferKey,
    usage: Usage,
) {
    let report_id = Uuid::new_v4();
    let exchange_id = Uuid::new_v4().to_string();
    let tokens = [
        usage.input_tokens,
        usage.output_tokens,
        usage.cached_input_tokens,
        usage.cache_creation_input_tokens,
    ]
    .map(|tokens| i64::try_from(tokens.unwrap_or(0)));
    let [
        Ok(input_tokens),
        Ok(output_tokens),
        Ok(cache_read_tokens),
        Ok(cache_creation_tokens),
    ] = tokens
    else {
        tracing::warn!(
            parent: &span,
            event = "run_usage",
            outcome = "lost",
            reason = "token_overflow"
        );
        return;
    };
    let report = UsageReport {
        occurred_at: chrono::Utc::now(),
        models: vec![ModelUsage {
            model_source_id: offer.source_id,
            upstream_model_id: offer.upstream_model_id,
            input_tokens,
            output_tokens,
            cache_read_tokens,
            cache_creation_tokens,
        }],
    };
    // Only the bounded accounting write survives a disconnected browser.
    // It starts before yielding the response; inference itself is never spawned.
    tokio::spawn(
        async move {
            let failure = match tokio::time::timeout(
                std::time::Duration::from_secs(2),
                persist_usage(&pool, provenance, &exchange_id, report_id, report),
            )
            .await
            {
                Ok(Ok(())) => return,
                Ok(Err(_)) => "write_failed",
                Err(_) => "timeout",
            };
            tracing::warn!(event = "run_usage", outcome = "lost", reason = failure, %report_id);
        }
        .instrument(span),
    );
}
