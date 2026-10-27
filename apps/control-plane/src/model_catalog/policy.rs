// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! SQL decisions only. Permission is not evidence of pod execution readiness.

use std::collections::BTreeSet;

use axum::http::StatusCode;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::{PgConnection, types::Json};
use utoipa::ToSchema;
use uuid::Uuid;

use crate::error::{AppError, AppResult};

#[derive(
    Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Deserialize, Serialize, ToSchema, sqlx::FromRow,
)]
#[serde(deny_unknown_fields)]
pub struct ModelOfferKey {
    pub source_id: String,
    pub upstream_model_id: String,
}

#[derive(Serialize, ToSchema)]
pub struct OrganizationModelPolicy {
    pub organization_id: Uuid,
    /// Zero means no saved policy: no permissions or implicit selections.
    pub revision: i64,
    pub permitted: Vec<ModelOfferKey>,
    /// Organization ceiling, independent of the user's per-question choice.
    #[schema(max_items = 4096)]
    pub reasoning_enabled: Vec<ModelOfferKey>,
    pub default: Option<ModelOfferKey>,
    pub fallback: Option<ModelOfferKey>,
    pub created_by: Option<String>,
    pub created_at: Option<DateTime<Utc>>,
    pub updated_by: Option<String>,
    pub updated_at: Option<DateTime<Utc>>,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ReplaceModelPolicy {
    #[schema(minimum = 0)]
    pub expected_revision: i64,
    #[schema(max_items = 4096)]
    pub permitted: Vec<ModelOfferKey>,
    /// Organization ceiling, independent of the user's per-question choice.
    #[schema(max_items = 4096)]
    pub reasoning_enabled: Vec<ModelOfferKey>,
    /// Required; null explicitly clears the choice. This is a complete replacement.
    #[serde(deserialize_with = "Option::deserialize")]
    #[schema(required = true)]
    pub default: Option<ModelOfferKey>,
    #[serde(deserialize_with = "Option::deserialize")]
    #[schema(required = true)]
    pub fallback: Option<ModelOfferKey>,
}

#[derive(sqlx::FromRow)]
struct PolicyRow {
    revision: i64,
    default_source_id: Option<String>,
    default_upstream_model_id: Option<String>,
    fallback_source_id: Option<String>,
    fallback_upstream_model_id: Option<String>,
    created_by: String,
    created_at: DateTime<Utc>,
    updated_by: String,
    updated_at: DateTime<Utc>,
}

fn key(source: Option<String>, upstream: Option<String>) -> Option<ModelOfferKey> {
    source
        .zip(upstream)
        .map(|(source_id, upstream_model_id)| ModelOfferKey {
            source_id,
            upstream_model_id,
        })
}

/// Caller supplies a consistent read snapshot or the existing organization write lock.
pub(super) async fn read(
    conn: &mut PgConnection,
    organization_id: Uuid,
) -> AppResult<OrganizationModelPolicy> {
    let row: Option<PolicyRow> = sqlx::query_as(
        "select revision, default_source_id, default_upstream_model_id,
             fallback_source_id, fallback_upstream_model_id, created_by, created_at, updated_by, updated_at
         from organization_model_policy where organization_id = $1",
    ).bind(organization_id).fetch_optional(&mut *conn).await?;
    let permissions: Vec<(String, String, bool)> = sqlx::query_as(
        "select source_id, upstream_model_id, reasoning_enabled from organization_model_permission
         where organization_id = $1 order by source_id, upstream_model_id",
    )
    .bind(organization_id)
    .fetch_all(conn)
    .await?;
    let mut permitted = Vec::with_capacity(permissions.len());
    let mut reasoning_enabled = Vec::new();
    for (source_id, upstream_model_id, enabled) in permissions {
        let key = ModelOfferKey {
            source_id,
            upstream_model_id,
        };
        if enabled {
            reasoning_enabled.push(key.clone());
        }
        permitted.push(key);
    }
    Ok(match row {
        Some(row) => OrganizationModelPolicy {
            organization_id,
            revision: row.revision,
            permitted,
            reasoning_enabled,
            default: key(row.default_source_id, row.default_upstream_model_id),
            fallback: key(row.fallback_source_id, row.fallback_upstream_model_id),
            created_by: Some(row.created_by),
            created_at: Some(row.created_at),
            updated_by: Some(row.updated_by),
            updated_at: Some(row.updated_at),
        },
        None => OrganizationModelPolicy {
            organization_id,
            revision: 0,
            permitted,
            reasoning_enabled,
            default: None,
            fallback: None,
            created_by: None,
            created_at: None,
            updated_by: None,
            updated_at: None,
        },
    })
}

impl ReplaceModelPolicy {
    fn validate(&self) -> AppResult<BTreeSet<ModelOfferKey>> {
        let permitted: BTreeSet<_> = self.permitted.iter().cloned().collect();
        if self.expected_revision < 0
            || self.permitted.len() > 4096
            || self.reasoning_enabled.len() > 4096
            || permitted.len() != self.permitted.len()
        {
            return Err(AppError::Unprocessable(
                "invalid revision, duplicate keys or too many permitted offers".into(),
            ));
        }
        let reasoning: BTreeSet<_> = self.reasoning_enabled.iter().cloned().collect();
        if reasoning.len() != self.reasoning_enabled.len() || !reasoning.is_subset(&permitted) {
            return Err(AppError::Unprocessable(
                "reasoning must name distinct permitted offers".into(),
            ));
        }
        for offer in &permitted {
            if !super::config::bounded_text(&offer.source_id, 64)
                || !offer
                    .source_id
                    .starts_with(|c: char| c.is_ascii_alphanumeric())
                || !offer
                    .source_id
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || b"._-".contains(&c))
                || !super::config::bounded_text(&offer.upstream_model_id, 256)
            {
                return Err(AppError::Unprocessable("invalid offer identity".into()));
            }
        }
        if [&self.default, &self.fallback]
            .into_iter()
            .flatten()
            .any(|choice| !permitted.contains(choice))
        {
            return Err(AppError::Unprocessable("default and fallback must be permitted; clear or replace revoked choices explicitly".into()));
        }
        Ok(permitted)
    }
}

#[derive(sqlx::FromRow)]
struct Candidate {
    source_id: String,
    upstream_model_id: String,
    eligible: bool,
}

/// Locks only newly permitted/selected offers and their sources, in source/key order.
/// Publication and configuration cannot invalidate the facts before this policy commits.
pub(super) async fn require_selectable(
    conn: &mut PgConnection,
    candidates: &BTreeSet<ModelOfferKey>,
) -> AppResult<()> {
    if candidates.is_empty() {
        return Ok(());
    }
    let rows: Vec<Candidate> = sqlx::query_as(
        "select o.source_id, o.upstream_model_id,
             coalesce((s.configuration->>'enabled')::boolean and s.state = 'ok'
                 and s.snapshot_source_revision = (s.configuration->>'revision')::bigint
                 and o.advertised and o.metadata->'chat' = 'true'::jsonb, false) as eligible
         from model_source s join model_offer o on o.source_id = s.source_id
         join jsonb_to_recordset($1) as x(source_id text, upstream_model_id text)
             on (o.source_id, o.upstream_model_id) = (x.source_id, x.upstream_model_id)
         order by s.source_id, o.upstream_model_id for share of s, o",
    )
    .bind(Json(candidates))
    .fetch_all(conn)
    .await?;
    let found: BTreeSet<_> = rows
        .iter()
        .map(|row| ModelOfferKey {
            source_id: row.source_id.clone(),
            upstream_model_id: row.upstream_model_id.clone(),
        })
        .collect();
    if found != *candidates {
        return Err(AppError::problem(
            StatusCode::UNPROCESSABLE_ENTITY,
            "unknown_model_offer",
            "A newly permitted or selected offer does not exist.",
        ));
    }
    if rows.iter().any(|row| !row.eligible) {
        return Err(AppError::problem(
            StatusCode::CONFLICT,
            "model_offer_not_selectable",
            "New permissions and selections require a present chat offer successfully observed at the current enabled source revision.",
        ));
    }
    Ok(())
}

/// The caller owns the authorized transaction and its platform/organization lock.
pub(super) async fn replace(
    conn: &mut PgConnection,
    organization_id: Uuid,
    uid: &str,
    request: ReplaceModelPolicy,
) -> AppResult<OrganizationModelPolicy> {
    let permitted = request.validate()?;
    let current = read(conn, organization_id).await?;
    if current.revision != request.expected_revision {
        return Err(AppError::problem(
            StatusCode::CONFLICT,
            "model_policy_revision_conflict",
            "Model policy changed; reload it before replacing it.",
        ));
    }
    let previous: BTreeSet<_> = current.permitted.into_iter().collect();
    let mut candidates: BTreeSet<_> = permitted.difference(&previous).cloned().collect();
    for (choice, old) in [
        (&request.default, &current.default),
        (&request.fallback, &current.fallback),
    ] {
        if choice != old
            && let Some(choice) = choice
        {
            candidates.insert(choice.clone());
        }
    }
    let previous_reasoning: BTreeSet<_> = current.reasoning_enabled.into_iter().collect();
    let reasoning: BTreeSet<_> = request.reasoning_enabled.into_iter().collect();
    let newly_enabled: BTreeSet<_> = reasoning.difference(&previous_reasoning).cloned().collect();
    candidates.extend(newly_enabled.iter().cloned());
    require_selectable(conn, &candidates).await?;
    if !newly_enabled.is_empty() {
        let supported: i64 = sqlx::query_scalar(
            "select count(*) from model_offer o
             join jsonb_to_recordset($1) as x(source_id text, upstream_model_id text)
                 on (o.source_id, o.upstream_model_id) = (x.source_id, x.upstream_model_id)
             where o.metadata->'reasoning' = 'true'::jsonb",
        )
        .bind(Json(&newly_enabled))
        .fetch_one(&mut *conn)
        .await?;
        if supported != newly_enabled.len() as i64 {
            return Err(AppError::Unprocessable(
                "reasoning requires a source-reported reasoning-capable offer".into(),
            ));
        }
    }
    let revision = current
        .revision
        .checked_add(1)
        .ok_or_else(|| AppError::Conflict("model policy revision exhausted".into()))?;
    sqlx::query(
        "insert into organization_model_policy
             (organization_id, revision, default_source_id, default_upstream_model_id,
              fallback_source_id, fallback_upstream_model_id, created_by, updated_by)
         values ($1, $2, $3, $4, $5, $6, $7, $7)
         on conflict (organization_id) do update set revision = excluded.revision,
             default_source_id = excluded.default_source_id,
             default_upstream_model_id = excluded.default_upstream_model_id,
             fallback_source_id = excluded.fallback_source_id,
             fallback_upstream_model_id = excluded.fallback_upstream_model_id,
             updated_by = excluded.updated_by, updated_at = now()",
    )
    .bind(organization_id)
    .bind(revision)
    .bind(request.default.as_ref().map(|k| &k.source_id))
    .bind(request.default.as_ref().map(|k| &k.upstream_model_id))
    .bind(request.fallback.as_ref().map(|k| &k.source_id))
    .bind(request.fallback.as_ref().map(|k| &k.upstream_model_id))
    .bind(uid)
    .execute(&mut *conn)
    .await?;
    let payload = Json(&permitted);
    sqlx::query(
        "delete from organization_model_permission p where organization_id = $1
         and not exists (select 1 from jsonb_to_recordset($2) as x(source_id text, upstream_model_id text)
             where (p.source_id, p.upstream_model_id) = (x.source_id, x.upstream_model_id))",
    ).bind(organization_id).bind(payload).execute(&mut *conn).await?;
    sqlx::query(
        "insert into organization_model_permission (organization_id, source_id, upstream_model_id)
         select $1, x.source_id, x.upstream_model_id
         from jsonb_to_recordset($2) as x(source_id text, upstream_model_id text)
         on conflict do nothing",
    )
    .bind(organization_id)
    .bind(payload)
    .execute(&mut *conn)
    .await?;
    sqlx::query(
        "update organization_model_permission p set reasoning_enabled = exists (
             select 1 from jsonb_to_recordset($2) as x(source_id text, upstream_model_id text)
             where (p.source_id, p.upstream_model_id) = (x.source_id, x.upstream_model_id))
         where organization_id = $1",
    )
    .bind(organization_id)
    .bind(Json(&reasoning))
    .execute(&mut *conn)
    .await?;
    read(conn, organization_id).await
}
