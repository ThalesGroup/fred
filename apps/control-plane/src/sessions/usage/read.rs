// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! One journal aggregation, shared by compatible named analytics results.
use chrono::{DateTime, Utc};
use sqlx::PgConnection;
use uuid::Uuid;

use crate::{analytics::models::AnalyticsInterval, error::AppResult};

// Immutable placement and retained deletion receipts attribute purged spaces to one organization.
macro_rules! organization_spaces {
    ($org:literal) => {
        concat!(
            "select id from space where organization_id=",
            $org,
            " union select target_id from deletion where organization_id=",
            $org,
            " and target_kind in ('organization','team','project','personal')",
            " union select target_parent_id from deletion where organization_id=",
            $org,
            " and target_kind='session' and target_parent_id is not null"
        )
    };
}
pub(crate) use organization_spaces;

/// Constructed only after authorization. An explicit team expands inside SQL,
/// including deletion receipts; no absent/empty list can become global.
pub(crate) enum UsageScope<'a> {
    Person {
        subject: &'a str,
        organization: Uuid,
    },
    Space {
        id: Uuid,
        team: bool,
    },
}

#[derive(sqlx::FromRow)]
pub(crate) struct AggregateRow {
    pub start: Option<DateTime<Utc>>,
    pub agent_instance_id: Option<Uuid>,
    pub space_id: Option<Uuid>,
    pub display_name: Option<String>,
    pub model_source_id: Option<String>,
    pub upstream_model_id: Option<String>,
    pub recorded_exchanges: String,
    pub input_tokens: String,
    pub output_tokens: String,
    pub cache_read_tokens: String,
    pub cache_creation_tokens: String,
    pub total_tokens: String,
    pub estimates: sqlx::types::Json<
        std::collections::BTreeMap<
            crate::analytics::models::ConsumptionMeasure,
            crate::analytics::models::AnalyticsEstimate,
        >,
    >,
}

pub(crate) async fn read(
    conn: &mut PgConnection,
    scope: &UsageScope<'_>,
    since: DateTime<Utc>,
    until: DateTime<Utc>,
    interval: AnalyticsInterval,
    group_limit: usize,
) -> AppResult<Vec<AggregateRow>> {
    // Keep the subject/space predicates indexable, including with generic plans.
    // A limit bounds returned rows, not scans: the caller also sets a SQL timeout.
    let query = match scope {
        UsageScope::Person { subject, organization } => sqlx::query_as::<_, AggregateRow>(concat!(
            "with scoped as not materialized (select * from model_usage where user_id=$1 and space_id in (",
            organization_spaces!("$7"), "))",
            include_str!("read.sql")
        ))
        .bind(subject)
        .bind(since)
        .bind(until)
        .bind(interval.as_str())
        .bind(group_limit as i64 + 1)
        .bind(crate::analytics::factors::catalog()?)
        .bind(organization),
        UsageScope::Space { id, team } => sqlx::query_as::<_, AggregateRow>(concat!(
            "with scoped as not materialized (select * from model_usage where space_id in (
                select $1::uuid union select id from space where parent_id=$1 and kind='project' and $7
                union select target_id from deletion where target_parent_id=$1 and target_kind='project' and $7))",
            include_str!("read.sql")
        ))
        .bind(id)
        .bind(since)
        .bind(until)
        .bind(interval.as_str())
        .bind(group_limit as i64 + 1)
        .bind(crate::analytics::factors::catalog()?)
        .bind(team),
    };
    Ok(query.fetch_all(conn).await?)
}
