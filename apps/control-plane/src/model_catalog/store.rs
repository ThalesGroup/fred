// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use anyhow::{Context, Result, ensure};
use chrono::{DateTime, Utc};
use serde::Serialize;
use sqlx::{PgConnection, PgPool, types::Json};
use utoipa::ToSchema;
use uuid::Uuid;

use super::{
    config::{ModelSource, validate_sources},
    discovery::{self, DiscoveredOffer, DiscoveryFailure, ModelMetadata},
};

#[derive(sqlx::FromRow)]
struct SourceRow {
    configuration: Json<ModelSource>,
    refresh_token: Option<Uuid>,
}

#[derive(Debug, Clone, Serialize, ToSchema, sqlx::FromRow)]
pub struct ModelObservation {
    pub source_id: String,
    pub source_revision: i64,
    pub enabled: bool,
    pub state: String,
    pub error_code: Option<String>,
    pub checked_at: Option<DateTime<Utc>>,
    pub last_success_at: Option<DateTime<Utc>>,
    pub snapshot_revision: i64,
    pub snapshot_source_revision: Option<i64>,
}

#[derive(Debug, Serialize, ToSchema, sqlx::FromRow)]
pub struct StoredModelOffer {
    pub source_id: String,
    pub upstream_model_id: String,
    #[schema(value_type = ModelMetadata)]
    pub metadata: Json<ModelMetadata>,
    pub first_seen_at: DateTime<Utc>,
    pub last_seen_at: DateTime<Utc>,
    pub advertised: bool,
    pub withdrawn_at: Option<DateTime<Utc>>,
}

#[derive(Serialize, ToSchema)]
pub struct ModelInventory {
    pub observation: ModelObservation,
    pub offers: Vec<StoredModelOffer>,
}

#[derive(Debug)]
pub enum RefreshResult {
    Published,
    Failed(DiscoveryFailure),
    /// Another refresh started, or source configuration changed, before publication.
    Superseded,
}

/// Apply deployment approvals without network access or credential lookup.
/// Disable before removal; retained rows prevent source identity/revision reuse.
/// Operator scope and rotation obligations are documented in the component README.
pub async fn configure_sources(pool: &PgPool, sources: &[ModelSource]) -> Result<()> {
    validate_sources(sources)?;
    let mut tx = pool.begin().await?;
    // Serialize deployment configuration only, never the HTTP discovery phase.
    sqlx::query("select pg_advisory_xact_lock(hashtextextended('platform_model_sources', 0))")
        .execute(&mut *tx)
        .await?;
    let stored: Vec<SourceRow> = sqlx::query_as(
        "select configuration, refresh_token from model_source order by source_id for update",
    )
    .fetch_all(&mut *tx)
    .await?;
    for row in &stored {
        let previous = &row.configuration.0;
        ensure!(
            !previous.enabled || sources.iter().any(|s| s.source_id == previous.source_id),
            "disable an enabled model source with a higher revision before removing its configuration"
        );
    }
    for source in sources {
        if let Some(row) = stored
            .iter()
            .find(|r| r.configuration.source_id == source.source_id)
        {
            let previous = &row.configuration.0;
            ensure!(
                previous.same_identity(source),
                "changed model source destination/account/namespace requires a new source_id"
            );
            ensure!(
                source.revision >= previous.revision,
                "obsolete model source revision"
            );
            if source.revision == previous.revision {
                ensure!(
                    source == previous,
                    "changed model source configuration requires a higher revision"
                );
                continue;
            }
        }
        sqlx::query(
            "insert into model_source (source_id, configuration) values ($1, $2)
             on conflict (source_id) do update set configuration = excluded.configuration,
                 refresh_token = null, state = 'not_observed', checked_at = null, error_code = null"
        ).bind(&source.source_id).bind(Json(source)).execute(&mut *tx).await?;
    }
    tx.commit().await?;
    Ok(())
}

/// Refresh an exactly matching platform approval; callers own authorization.
/// Latest claimed token wins across processes, even after failure/cancellation.
/// HTTP is outside SQL; configuration changes fence publication (see README).
pub async fn refresh(pool: &PgPool, source: &ModelSource) -> Result<RefreshResult> {
    let mut tx = pool.begin().await?;
    let token = claim(&mut tx, source)
        .await?
        .context("obsolete model source configuration")?;
    tx.commit().await?;
    let result = discovery::discover(source).await;
    let mut tx = pool.begin().await?;
    let outcome = publish(&mut tx, source, token, result).await?;
    tx.commit().await?;
    Ok(outcome)
}

/// The caller owns the transaction, including any administrative authorization.
pub(super) async fn claim(conn: &mut PgConnection, source: &ModelSource) -> Result<Option<Uuid>> {
    source.validate()?;
    ensure!(source.enabled, "model source disabled");
    let row: Option<SourceRow> = sqlx::query_as(
        "select configuration, refresh_token from model_source where source_id = $1 for update",
    )
    .bind(&source.source_id)
    .fetch_optional(&mut *conn)
    .await?;
    if !row.is_some_and(|row| row.configuration.0 == *source) {
        return Ok(None);
    }
    let token = Uuid::new_v4();
    sqlx::query("update model_source set refresh_token = $2 where source_id = $1")
        .bind(&source.source_id)
        .bind(token)
        .execute(conn)
        .await?;
    Ok(Some(token))
}

/// Never commits: the administrative caller must authorize/fence before publication.
pub(super) async fn publish(
    conn: &mut PgConnection,
    source: &ModelSource,
    token: Uuid,
    result: Result<Vec<DiscoveredOffer>, DiscoveryFailure>,
) -> Result<RefreshResult> {
    let row: SourceRow = sqlx::query_as(
        "select configuration, refresh_token from model_source where source_id = $1 for update",
    )
    .bind(&source.source_id)
    .fetch_one(&mut *conn)
    .await?;
    if row.configuration.0 != *source || row.refresh_token != Some(token) {
        return Ok(RefreshResult::Superseded);
    }
    let now = Utc::now();
    let outcome = match result {
        Ok(offers) => {
            // One bounded batch, rather than one SQL round-trip per model. This JSON
            // contains only normalized metadata and exact IDs, not the raw response.
            let payload = Json(serde_json::to_value(&offers)?);
            sqlx::query(
                "update model_offer o set advertised = false, withdrawn_at = $3
                 where o.source_id = $1 and o.advertised and not exists (
                     select 1 from jsonb_to_recordset($2) as x(upstream_model_id text)
                     where x.upstream_model_id = o.upstream_model_id)",
            )
            .bind(&source.source_id)
            .bind(&payload)
            .bind(now)
            .execute(&mut *conn)
            .await?;
            sqlx::query(
                "insert into model_offer
                    (source_id, upstream_model_id, metadata, first_seen_at, last_seen_at, advertised)
                 select $1, x.upstream_model_id, x.metadata, $3, $3, true
                 from jsonb_to_recordset($2) as x(upstream_model_id text, metadata jsonb)
                 on conflict (source_id, upstream_model_id) do update set
                     metadata = excluded.metadata, last_seen_at = excluded.last_seen_at,
                     advertised = true, withdrawn_at = null"
            ).bind(&source.source_id).bind(&payload).bind(now).execute(&mut *conn).await?;
            sqlx::query(
                "update model_source set state = 'ok', error_code = null, checked_at = $2,
                     last_success_at = $2, snapshot_revision = snapshot_revision + 1,
                     snapshot_source_revision = $3, refresh_token = null where source_id = $1",
            )
            .bind(&source.source_id)
            .bind(now)
            .bind(source.revision)
            .execute(&mut *conn)
            .await?;
            RefreshResult::Published
        }
        Err(error) => {
            sqlx::query(
                "update model_source set state = $2, error_code = $3, checked_at = $4,
                     refresh_token = null where source_id = $1",
            )
            .bind(&source.source_id)
            .bind(error.state())
            .bind(error.to_string())
            .bind(now)
            .execute(&mut *conn)
            .await?;
            RefreshResult::Failed(error)
        }
    };
    Ok(outcome)
}

/// Consistent observation + offers; internal callers own authorization.
pub async fn inventory(pool: &PgPool, source_id: &str) -> Result<Option<ModelInventory>> {
    let mut tx = pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let result = read_inventory(&mut tx, Some(source_id)).await?.pop();
    tx.commit().await?;
    Ok(result)
}

/// Two bounded-by-inventory queries in the caller's snapshot, with no private configuration.
pub(super) async fn read_inventory(
    conn: &mut PgConnection,
    source_id: Option<&str>,
) -> Result<Vec<ModelInventory>> {
    let observations: Vec<ModelObservation> = sqlx::query_as(
        "select source_id, (configuration->>'revision')::bigint as source_revision,
             (configuration->>'enabled')::boolean as enabled, state, error_code, checked_at,
             last_success_at, snapshot_revision, snapshot_source_revision
         from model_source where ($1::text is null or source_id = $1) order by source_id",
    )
    .bind(source_id)
    .fetch_all(&mut *conn)
    .await?;
    let offers: Vec<StoredModelOffer> = sqlx::query_as(
        "select source_id, upstream_model_id, metadata, first_seen_at, last_seen_at,
             advertised, withdrawn_at from model_offer
         where ($1::text is null or source_id = $1) order by source_id, upstream_model_id",
    )
    .bind(source_id)
    .fetch_all(conn)
    .await?;
    let mut by_source = std::collections::BTreeMap::<String, Vec<StoredModelOffer>>::new();
    for offer in offers {
        by_source
            .entry(offer.source_id.clone())
            .or_default()
            .push(offer);
    }
    Ok(observations
        .into_iter()
        .map(|observation| ModelInventory {
            offers: by_source.remove(&observation.source_id).unwrap_or_default(),
            observation,
        })
        .collect())
}
