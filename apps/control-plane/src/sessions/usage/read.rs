// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use axum::{Json, extract::State};
use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};
use sqlx::PgPool;
use utoipa::{IntoParams, ToSchema};
use uuid::Uuid;

use crate::{
    api::AppState,
    auth::CurrentUser,
    authorization,
    domain::SpaceKind,
    error::{AppError, AppResult},
    extract::{ApiPath, ApiQuery},
    onboarding::AdmittedUser,
    roles::SpacePermission,
};

#[derive(Default, Deserialize, IntoParams)]
#[serde(deny_unknown_fields)]
#[into_params(parameter_in = Query)]
struct UsageRange {
    /// Inclusive ISO 8601 instant with offset; defaults to 30 days before until.
    since: Option<DateTime<Utc>>,
    /// Exclusive ISO 8601 instant with offset; defaults to now. Maximum range: 366 days.
    until: Option<DateTime<Utc>>,
}

impl UsageRange {
    fn resolve(
        self,
        now: DateTime<Utc>,
    ) -> AppResult<(DateTime<Utc>, DateTime<Utc>, UsageInterval)> {
        let until = self.until.unwrap_or(now);
        let since = self
            .since
            .or_else(|| until.checked_sub_signed(Duration::days(30)))
            .ok_or_else(|| AppError::Unprocessable("Invalid usage range.".into()))?;
        let duration = until - since;
        if duration <= Duration::zero() || duration > Duration::days(366) {
            return Err(AppError::Unprocessable(
                "Usage requires since < until and a range of at most 366 days.".into(),
            ));
        }
        let interval = if duration <= Duration::hours(48) {
            UsageInterval::Hour
        } else if duration <= Duration::days(92) {
            UsageInterval::Day
        } else {
            UsageInterval::Week
        };
        Ok((since, until, interval))
    }
}

/// UTC buckets: hour up to 48 hours, day up to 92 days, week beyond.
/// Weeks start on Monday. Empty buckets contain zeros.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "lowercase")]
enum UsageInterval {
    Hour,
    Day,
    Week,
}

impl UsageInterval {
    fn as_str(self) -> &'static str {
        match self {
            Self::Hour => "hour",
            Self::Day => "day",
            Self::Week => "week",
        }
    }
}

#[derive(Default, Serialize, ToSchema, sqlx::FromRow)]
struct UsageTotals {
    /// Distinct (session_id, exchange_id) whose first consumption falls in the range.
    /// HITL resumes add tokens, never another turn.
    turns: i64,
    input_tokens: i64,
    output_tokens: i64,
    cache_read_tokens: i64,
    cache_creation_tokens: i64,
}

#[derive(Serialize, ToSchema)]
struct UsagePoint {
    /// Start of the UTC bucket; the first bucket may start before since.
    start: DateTime<Utc>,
    #[serde(flatten)]
    totals: UsageTotals,
}

#[derive(Serialize, ToSchema)]
struct AgentUsage {
    agent_instance_id: Uuid,
    /// Current instance name, latest retained session name, or null.
    #[schema(required)]
    display_name: Option<String>,
    /// Consumption space recorded in the journal.
    space_id: Uuid,
    #[serde(flatten)]
    totals: UsageTotals,
}

#[derive(Serialize, ToSchema)]
struct ModelUsageTotals {
    model_source_id: String,
    upstream_model_id: String,
    #[serde(flatten)]
    totals: UsageTotals,
}

#[derive(Serialize, ToSchema)]
struct UsageResponse {
    since: DateTime<Utc>,
    until: DateTime<Utc>,
    interval: UsageInterval,
    totals: UsageTotals,
    series: Vec<UsagePoint>,
    /// Sorted by input + output tokens descending. No per-user breakdown.
    by_agent: Vec<AgentUsage>,
    /// Sorted by input + output tokens descending; a turn may use several models.
    by_model: Vec<ModelUsageTotals>,
}

#[derive(sqlx::FromRow)]
struct AggregateRow {
    start: Option<DateTime<Utc>>,
    agent_instance_id: Option<Uuid>,
    space_id: Option<Uuid>,
    display_name: Option<String>,
    model_source_id: Option<String>,
    upstream_model_id: Option<String>,
    #[sqlx(flatten)]
    totals: UsageTotals,
}

pub(super) fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new()
        .routes(utoipa_axum::routes!(space_usage))
        .routes(utoipa_axum::routes!(my_usage))
}

/// Read team/project consumption with direct ReadUsage (Owner or Analyst).
/// A team includes its projects, even retired or purged ones, and their agent names,
/// without requiring roles in those projects. A project includes only itself.
/// Organization and personal spaces are unsupported. No per-user detail is returned.
#[utoipa::path(get, path = "/spaces/{space_id}/usage",
    params(("space_id" = Uuid, Path), UsageRange),
    responses((status = 200, body = UsageResponse),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody))) ]
async fn space_usage(
    State(state): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space_id): ApiPath<Uuid>,
    ApiQuery(range): ApiQuery<UsageRange>,
) -> AppResult<Json<UsageResponse>> {
    let range = range.resolve(Utc::now())?;
    // Reuse the authorization facts and decision, checking the supported kind
    // as authorize_organization does before evaluating the permission.
    let facts = authorization::load_facts(&state.pool, &user.uid, space_id).await?;
    if !facts.in_organization {
        return Err(AppError::NotFound);
    }
    if !matches!(facts.space.kind, SpaceKind::Team | SpaceKind::Project) {
        return Err(AppError::Unprocessable("team or project required".into()));
    }
    authorization::decide(&facts, SpacePermission::ReadUsage)?;
    let ids = if facts.space.kind == SpaceKind::Team {
        // Receipts preserve the parent of individually purged projects. No
        // activity predicate: retirement does not remove consumed tokens.
        sqlx::query_scalar(
            "select $1::uuid union select id from space where parent_id=$1 and kind='project'
             union select target_id from deletion where target_parent_id=$1 and target_kind='project'",
        )
        .bind(space_id)
        .fetch_all(&state.pool)
        .await?
    } else {
        vec![space_id]
    };
    Ok(Json(read(&state.pool, &user.uid, Some(&ids), range).await?))
}

/// Read only the authenticated person's consumption across all spaces, including
/// spaces they can no longer access. No role, admission or consent check is required.
/// Tokens follow their consumption time; each turn belongs to its first consumption.
#[utoipa::path(get, path = "/me/usage", params(UsageRange),
    responses((status = 200, body = UsageResponse),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody))) ]
async fn my_usage(
    State(state): State<AppState>,
    user: CurrentUser,
    ApiQuery(range): ApiQuery<UsageRange>,
) -> AppResult<Json<UsageResponse>> {
    // OwnUser rejects all query strings; here ApiQuery permits only the date
    // range, while retaining its person-only boundary and no admission check.
    if user.service_account || user.roles.iter().any(|role| role == "service_agent") {
        return Err(AppError::Forbidden);
    }
    Ok(Json(
        read(&state.pool, &user.uid, None, range.resolve(Utc::now())?).await?,
    ))
}

async fn read(
    pool: &PgPool,
    user: &str,
    spaces: Option<&[Uuid]>,
    (since, until, interval): (DateTime<Utc>, DateTime<Utc>, UsageInterval),
) -> AppResult<UsageResponse> {
    // Keep both predicates indexable, including when PostgreSQL uses a generic
    // plan. NOT MATERIALIZED lets range and prior-turn scans use the same index.
    let query = if let Some(ids) = spaces {
        sqlx::query_as::<_, AggregateRow>(concat!(
            "with scoped as not materialized (select * from model_usage where space_id=any($1))",
            include_str!("read.sql")
        ))
        .bind(ids)
    } else {
        sqlx::query_as::<_, AggregateRow>(concat!(
            "with scoped as not materialized (select * from model_usage where user_id=$1)",
            include_str!("read.sql")
        ))
        .bind(user)
    };
    let rows = query
        .bind(since)
        .bind(until)
        .bind(interval.as_str())
        .fetch_all(pool)
        .await?;
    let mut response = UsageResponse {
        since,
        until,
        interval,
        totals: UsageTotals::default(),
        series: Vec::new(),
        by_agent: Vec::new(),
        by_model: Vec::new(),
    };
    for row in rows {
        match (
            row.start,
            row.agent_instance_id,
            row.space_id,
            row.model_source_id,
            row.upstream_model_id,
        ) {
            (None, None, None, None, None) => response.totals = row.totals,
            (Some(start), None, None, None, None) => response.series.push(UsagePoint {
                start,
                totals: row.totals,
            }),
            (None, Some(agent_instance_id), Some(space_id), None, None) => {
                response.by_agent.push(AgentUsage {
                    agent_instance_id,
                    space_id,
                    display_name: row.display_name,
                    totals: row.totals,
                })
            }
            (None, None, None, Some(model_source_id), Some(upstream_model_id)) => {
                response.by_model.push(ModelUsageTotals {
                    model_source_id,
                    upstream_model_id,
                    totals: row.totals,
                })
            }
            _ => return Err(anyhow::anyhow!("invalid usage aggregate shape").into()),
        }
    }
    Ok(response)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_limits_and_interval_boundaries() {
        let now = "2026-06-01T12:34:56Z".parse::<DateTime<Utc>>().unwrap();
        assert_eq!(
            UsageRange::default().resolve(now).unwrap(),
            (now - Duration::days(30), now, UsageInterval::Day)
        );
        for (duration, expected) in [
            (Duration::hours(48), UsageInterval::Hour),
            (
                Duration::hours(48) + Duration::seconds(1),
                UsageInterval::Day,
            ),
            (Duration::days(92), UsageInterval::Day),
            (
                Duration::days(92) + Duration::seconds(1),
                UsageInterval::Week,
            ),
            (Duration::days(366), UsageInterval::Week),
        ] {
            let range = UsageRange {
                since: Some(now - duration),
                until: Some(now),
            };
            assert_eq!(range.resolve(now).unwrap().2, expected);
        }
        for duration in [
            Duration::zero(),
            Duration::seconds(-1),
            Duration::days(366) + Duration::seconds(1),
        ] {
            assert!(
                UsageRange {
                    since: Some(now - duration),
                    until: Some(now)
                }
                .resolve(now)
                .is_err()
            );
        }
        let past = now - Duration::days(60);
        assert_eq!(
            UsageRange {
                since: None,
                until: Some(past)
            }
            .resolve(now)
            .unwrap()
            .0,
            past - Duration::days(30)
        );
    }
}
