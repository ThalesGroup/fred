// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use std::collections::HashSet;

use axum::{
    extract::State,
    http::{HeaderMap, StatusCode},
};
use chrono::{DateTime, Utc};
use serde::Deserialize;
use utoipa::ToSchema;
use uuid::Uuid;

use crate::{
    api::AppState,
    authorization::RuntimeCaller,
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath, ApiQuery, idempotency_key},
    model_catalog::config::valid_source_id,
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct UsageQuery {}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UsageReport {
    /// Time of consumption; at most five minutes ahead of server time.
    pub occurred_at: DateTime<Utc>,
    /// Complete set of distinct offers consumed during this report (one run); order is irrelevant.
    #[schema(min_items = 1, max_items = 8)]
    pub models: Vec<ModelUsage>,
}

#[derive(Deserialize, ToSchema, sqlx::FromRow, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ModelUsage {
    /// Source identifier of the Weaver catalogue offer; retained after its removal.
    #[schema(
        min_length = 1,
        max_length = 64,
        pattern = "^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
    )]
    pub model_source_id: String,
    /// Upstream model identifier, 1 to 256 UTF-8 bytes, without surrounding whitespace.
    #[schema(min_length = 1, max_length = 256)]
    pub upstream_model_id: String,
    #[schema(minimum = 0)]
    pub input_tokens: i64,
    #[schema(minimum = 0)]
    pub output_tokens: i64,
    #[schema(minimum = 0)]
    pub cache_read_tokens: i64,
    #[schema(minimum = 0)]
    pub cache_creation_tokens: i64,
}

#[derive(sqlx::FromRow)]
struct StoredUsage {
    #[sqlx(flatten)]
    model: ModelUsage,
    same_report: bool,
}

pub(super) fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new().routes(utoipa_axum::routes!(record_usage))
}

/// Atomically record consumption reported by a trusted runtime workload in its own name.
/// Session provenance supplies the space, person and agent, including after retirement.
/// Idempotency-Key identifies the report: identical replays return 204; any difference returns idempotency_conflict.
/// Different keys may report consumption for the same exchange, including after a human-validation resume.
/// This records an admitted turn without renewing its admission or requiring a live agent.
#[utoipa::path(post, path = "/spaces/{space_id}/sessions/{session_id}/exchanges/{exchange_id}/usage",
    params(("Idempotency-Key" = Uuid, Header, description = "Caller-chosen consumption report UUID; required and unique per run"),
        ("space_id" = Uuid, Path), ("session_id" = Uuid, Path),
        ("exchange_id" = String, Path, min_length = 1, max_length = 256,
            description = "Turn identifier, without surrounding whitespace or control characters")),
    request_body = UsageReport,
    responses((status = 204, description = "Recorded or identical replay"),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, description = "A trusted runtime workload is required", body = crate::error::ErrorBody),
        (status = 404, description = "Session not found in this space", body = crate::error::ErrorBody),
        (status = 409, description = "idempotency_conflict: the report key already identifies a different consumption report", body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody))) ]
async fn record_usage(
    State(state): State<AppState>,
    RuntimeCaller(caller): RuntimeCaller,
    ApiQuery(_query): ApiQuery<UsageQuery>,
    ApiPath((space_id, session_id, exchange_id)): ApiPath<(Uuid, Uuid, String)>,
    headers: HeaderMap,
    ApiJson(body): ApiJson<UsageReport>,
) -> AppResult<StatusCode> {
    if !state.auth.accepts_runtime_delegation(&caller) {
        return Err(AppError::Forbidden);
    }
    let report_id = idempotency_key(&headers)?;
    let mut offers = HashSet::new();
    if !(1..=256).contains(&exchange_id.chars().count())
        || exchange_id.trim() != exchange_id
        || exchange_id.chars().any(char::is_control)
        || !(1..=8).contains(&body.models.len())
        || body.occurred_at > Utc::now() + chrono::Duration::minutes(5)
        || body.models.iter().any(|model| {
            !valid_source_id(&model.model_source_id)
                || !(1..=256).contains(&model.upstream_model_id.len())
                || model.upstream_model_id.trim() != model.upstream_model_id
                || model.upstream_model_id.contains('\0')
                || [
                    model.input_tokens,
                    model.output_tokens,
                    model.cache_read_tokens,
                    model.cache_creation_tokens,
                ]
                .iter()
                .any(|tokens| *tokens < 0)
                || !offers.insert((&model.model_source_id, &model.upstream_model_id))
        })
    {
        return Err(AppError::Unprocessable(
            "Invalid consumption report fields.".into(),
        ));
    }

    let mut tx = state.pool.begin().await?;
    // Serialize the entire set, including its initial absence, across all replicas.
    sqlx::query("select pg_advisory_xact_lock(hashtextextended($1, 0))")
        .bind(format!("model_usage:{report_id}"))
        .execute(&mut *tx)
        .await?;

    // No live-space, consent or deletion predicate: this is a fact from an admitted turn.
    let (space, user, agent): (Uuid, String, Uuid) = sqlx::query_as(
        "select space_id, user_id, agent_instance_id from session_metadata
         where session_id = $1 and space_id = $2",
    )
    .bind(session_id)
    .bind(space_id)
    .fetch_optional(&mut *tx)
    .await?
    .ok_or(AppError::NotFound)?;

    // Compare timestamps in PostgreSQL at the same precision used by insertion.
    let stored: Vec<StoredUsage> = sqlx::query_as(
        "select model_source_id, upstream_model_id, input_tokens, output_tokens,
            cache_read_tokens, cache_creation_tokens,
            session_id = $2 and exchange_id = $3 and occurred_at = $4
                and space_id = $5 and user_id = $6 and agent_instance_id = $7 as same_report
         from model_usage where report_id = $1",
    )
    .bind(report_id)
    .bind(session_id)
    .bind(&exchange_id)
    .bind(body.occurred_at)
    .bind(space)
    .bind(&user)
    .bind(agent)
    .fetch_all(&mut *tx)
    .await?;
    if stored.is_empty() {
        for model in &body.models {
            sqlx::query(
                "insert into model_usage (report_id, session_id, exchange_id, occurred_at, space_id, user_id,
                    agent_instance_id, model_source_id, upstream_model_id, input_tokens,
                    output_tokens, cache_read_tokens, cache_creation_tokens)
                 values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)",
            )
            .bind(report_id)
            .bind(session_id)
            .bind(&exchange_id)
            .bind(body.occurred_at)
            .bind(space)
            .bind(&user)
            .bind(agent)
            .bind(&model.model_source_id)
            .bind(&model.upstream_model_id)
            .bind(model.input_tokens)
            .bind(model.output_tokens)
            .bind(model.cache_read_tokens)
            .bind(model.cache_creation_tokens)
            .execute(&mut *tx)
            .await?;
        }
    } else if stored.len() != body.models.len()
        || stored
            .iter()
            .any(|row| !row.same_report || !body.models.contains(&row.model))
    {
        return Err(AppError::problem(
            StatusCode::CONFLICT,
            "idempotency_conflict",
            "A different consumption report already exists for this idempotency key.",
        ));
    }
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}
