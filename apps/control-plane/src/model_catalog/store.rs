// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use anyhow::{Context, Result, ensure};
use chrono::{DateTime, Utc};
use fred_rust_sdk::inference::{ModelConnection, ModelDialect, ModelWire};
use serde::Serialize;
use sqlx::{PgConnection, PgPool, types::Json};
use utoipa::ToSchema;
use uuid::Uuid;

use super::{
    config::{ModelSource, supports_transcription, validate_sources},
    discovery::{self, DiscoveredInventory, DiscoveryFailure, ModelMetadata},
    metadata::MetadataRefresh,
    policy::ModelUseOptions,
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
    /// `models_dev_unavailable` may accompany an otherwise successful provider observation.
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
    #[schema(value_type = ModelUseOptions, required = false)]
    pub uses: Json<ModelUseOptions>,
    pub first_seen_at: DateTime<Utc>,
    pub last_seen_at: DateTime<Utc>,
    pub advertised: bool,
    /// Server-calculated eligibility to authorize an advertised provider offer.
    #[sqlx(skip)]
    pub selectable: bool,
    pub withdrawn_at: Option<DateTime<Utc>>,
    #[schema(value_type = ModelMetadata)]
    pub detected_metadata: Json<ModelMetadata>,
    pub metadata_complements: serde_json::Value,
    pub metadata_revision: i64,
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct ModelInventory {
    #[sqlx(flatten)]
    pub observation: ModelObservation,
    #[sqlx(skip)]
    pub offers: Vec<StoredModelOffer>,
    pub name: String,
    pub url: Option<String>,
    pub metadata_provider: Option<String>,
    pub models_dev_enabled: bool,
    pub platform_terms_url: Option<String>,
    /// Public connection settings only; credentials and bindings stay private.
    pub api_root: String,
    #[sqlx(json)]
    pub dialect: ModelDialect,
    #[sqlx(json)]
    pub wire: ModelWire,
    pub managed: bool,
    #[serde(skip)]
    #[sqlx(json)]
    connection: ModelConnection,
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
        "select configuration, refresh_token from model_source where not managed order by source_id for update",
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
        let changed = sqlx::query(
            "insert into model_source (source_id, configuration) values ($1, $2)
             on conflict (source_id) do update set configuration = excluded.configuration,
                 refresh_token = null, state = 'not_observed', checked_at = null, error_code = null
             where not model_source.managed",
        )
        .bind(&source.source_id)
        .bind(Json(source))
        .execute(&mut *tx)
        .await?;
        ensure!(
            changed.rows_affected() == 1,
            "deployment source identity is reserved by an organization catalogue"
        );
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
    result: Result<DiscoveredInventory, DiscoveryFailure>,
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
        Ok(snapshot) => {
            // One bounded batch, rather than one SQL round-trip per model. This JSON
            // contains only normalized metadata and exact IDs, not the raw response.
            let payload = Json(serde_json::to_value(&snapshot.offers)?);
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
            // Carry forward registry facts for still-advertised IDs only when
            // enrichment was disabled or failed. Fresh provider facts win.
            sqlx::query(
                "insert into model_offer
                    (source_id, upstream_model_id, metadata, first_seen_at, last_seen_at, advertised)
                 select $1, x.upstream_model_id, x.metadata, $3, $3, true
                 from jsonb_to_recordset($2) as x(upstream_model_id text, metadata jsonb)
                 on conflict (source_id, upstream_model_id) do update set
                     metadata = case when $4 and model_offer.advertised then
                         excluded.metadata || (
                            select coalesce(jsonb_object_agg(p.key, model_offer.metadata->p.key), '{}'::jsonb)
                                || jsonb_build_object('provenance', excluded.metadata->'provenance'
                                    || coalesce(jsonb_object_agg(p.key, p.value), '{}'::jsonb))
                            from jsonb_each_text(model_offer.metadata->'provenance') p
                            where p.value = 'models_dev' and excluded.metadata->p.key = 'null'::jsonb
                                and (p.key <> 'chat' or excluded.metadata->'embedding' is distinct from 'true'::jsonb)
                                and (p.key not in ('reasoning_efforts', 'reasoning_transport')
                                    or excluded.metadata->'reasoning' is distinct from 'false'::jsonb)
                         ) else excluded.metadata end,
                     last_seen_at = excluded.last_seen_at,
                     advertised = true, withdrawn_at = null"
            )
            .bind(&source.source_id)
            .bind(&payload)
            .bind(now)
            .bind(snapshot.metadata_refresh != MetadataRefresh::Complete)
            .execute(&mut *conn)
            .await?;
            sqlx::query(
                "update model_source set state = 'ok', error_code = $4, checked_at = $2,
                     last_success_at = $2, snapshot_revision = snapshot_revision + 1,
                     snapshot_source_revision = $3, refresh_token = null where source_id = $1",
            )
            .bind(&source.source_id)
            .bind(now)
            .bind(source.revision)
            .bind(
                (snapshot.metadata_refresh == MetadataRefresh::Unavailable)
                    .then_some("models_dev_unavailable"),
            )
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
    let result = read_inventory(&mut tx, Some(source_id), None).await?.pop();
    tx.commit().await?;
    Ok(result)
}

/// Two bounded-by-inventory queries in the caller's snapshot. Connections stay internal.
pub(super) async fn read_inventory(
    conn: &mut PgConnection,
    source_id: Option<&str>,
    organization_id: Option<Uuid>,
) -> Result<Vec<ModelInventory>> {
    let observations: Vec<ModelInventory> = sqlx::query_as(
        "select source_id, (configuration->>'revision')::bigint as source_revision,
             (configuration->>'enabled')::boolean as enabled, state, error_code, checked_at,
             last_success_at, snapshot_revision, snapshot_source_revision,
             coalesce(c.name,s.source_id) as name, s.configuration->'inventory'->>'url' as url,
             s.configuration->>'metadata_provider' as metadata_provider,
             coalesce((s.configuration->>'models_dev_enabled')::boolean, true) as models_dev_enabled,
             s.configuration->>'platform_terms_url' as platform_terms_url,
             s.configuration->'inference'->>'api_root' as api_root,
             s.configuration->'inference'->'dialect' as dialect,
             s.configuration->'inference'->'wire' as wire, s.managed,
             s.configuration->'inference' as connection
         from model_source s left join organization_model_catalog c using(source_id)
         where (not s.managed or c.deleted_at is null and c.source_id is not null)
             and ($1::text is null or s.source_id = $1)
             and ($2::uuid is null or exists (select 1 from organization_model_source a
                 where a.organization_id = $2 and a.source_id = s.source_id)) order by source_id",
    )
    .bind(source_id)
    .bind(organization_id)
    .fetch_all(&mut *conn)
    .await?;
    let offers: Vec<StoredModelOffer> = sqlx::query_as(
        "select o.source_id, o.upstream_model_id, effective.metadata, model_use_options(effective.metadata) as uses, first_seen_at, last_seen_at,
             advertised, withdrawn_at,o.metadata as detected_metadata,coalesce(m.complements,'{}') as metadata_complements,coalesce(m.revision,0) as metadata_revision from model_offer o
         left join organization_model_metadata m on m.organization_id=$2 and m.source_id=o.source_id and m.upstream_model_id=o.upstream_model_id
         cross join lateral (select effective_model_metadata($2,o.source_id,o.upstream_model_id) as metadata) effective
         where o.source_id=any($1)
             and ($2::uuid is null or o.advertised or exists(select 1 from organization_model_permission p
                 where p.organization_id=$2 and p.source_id=o.source_id and p.upstream_model_id=o.upstream_model_id))
         order by o.source_id,o.upstream_model_id",
    )
    .bind(observations.iter().map(|source| &source.observation.source_id).collect::<Vec<_>>())
    .bind(organization_id)
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
        .map(|mut source| {
            let observation = &source.observation;
            let can_transcribe = supports_transcription(&source.connection);
            let mut offers = by_source.remove(&observation.source_id).unwrap_or_default();
            for offer in &mut offers {
                offer.uses.transcription &= can_transcribe;
                offer.selectable = super::policy::selectable(
                    observation.enabled,
                    observation.state == "ok",
                    observation.snapshot_source_revision == Some(observation.source_revision),
                    offer.advertised,
                );
            }
            source.offers = offers;
            source
        })
        .collect())
}
