// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Bounded named consumption and skill reads. Domain SQL remains in sessions::usage.
pub(crate) mod factors;
pub mod history;
pub(crate) mod models;
pub mod opensearch;

use std::collections::{BTreeMap, HashSet};

use axum::{
    Json,
    extract::{DefaultBodyLimit, State},
    http::StatusCode,
};
use chrono::{Datelike, Duration, Timelike};
use serde::Deserialize;
use sqlx::PgConnection;

use crate::{
    api::AppState,
    auth::CurrentUser,
    authorization,
    domain::SpaceKind,
    error::{AppError, AppResult},
    extract::{ApiJson, ApiQuery},
    onboarding,
    roles::SpacePermission,
    sessions::usage::read::{self, AggregateRow, UsageScope},
};
use models::*;

const MAX_POINTS: usize = 1000;
const MAX_ROWS: usize = 5000;
const MAX_RESPONSE_BYTES: usize = 2 * 1024 * 1024;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct NoQuery {}

pub fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new()
        .routes(utoipa_axum::routes!(query_analytics))
        .layer(DefaultBodyLimit::max(64 * 1024))
}

/// Named results from one source per batch. SQL uses one snapshot; history is independent.
/// Self requires person authentication and current work access to the explicit organization;
/// collective reads also require admission, current consent and direct ReadUsage.
/// No individual collective dimensions, arbitrary filters or non-UTC buckets.
/// Any authorization/source error fails the batch without returning partial data.
#[utoipa::path(post, path = "/analytics/query", request_body = AnalyticsRequest,
    responses((status = 200, body = AnalyticsResponse),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 413, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody))) ]
async fn query_analytics(
    State(state): State<AppState>,
    user: CurrentUser,
    ApiQuery(_query): ApiQuery<NoQuery>,
    ApiJson(request): ApiJson<AnalyticsRequest>,
) -> AppResult<Json<AnalyticsResponse>> {
    if user.service_account || user.roles.iter().any(|role| role == "service_agent") {
        return Err(AppError::Forbidden);
    }
    let plans = plan(&request)?;
    // Bounds pool waits, admission, all statements and serialization together.
    tokio::time::timeout(
        std::time::Duration::from_secs(10),
        execute(&state, &user, &request, &plans),
    )
    .await
    .map_err(|_| AppError::Unavailable("Analytics execution deadline exceeded".into()))?
    .map(Json)
}

struct ReadPlan {
    query: usize,
    interval: AnalyticsInterval,
    limit: usize,
    consumers: Vec<usize>,
}

fn invalid(detail: &str) -> AppError {
    AppError::Unprocessable(detail.into())
}

fn too_large() -> AppError {
    AppError::problem(
        StatusCode::UNPROCESSABLE_ENTITY,
        "query_too_large",
        "Analytics result exceeds the row or byte budget",
    )
}

fn interval(time: &AnalyticsPeriod) -> AnalyticsInterval {
    time.bucket.unwrap_or_else(|| {
        if time.until - time.since <= Duration::hours(48) {
            AnalyticsInterval::Hour
        } else if time.until - time.since <= Duration::days(92) {
            AnalyticsInterval::Day
        } else {
            AnalyticsInterval::Week
        }
    })
}

fn points(time: &AnalyticsPeriod, interval: AnalyticsInterval) -> usize {
    let since = time.since;
    let seconds = match interval {
        AnalyticsInterval::Hour => 3600,
        AnalyticsInterval::Day => 86400,
        AnalyticsInterval::Week => 604800,
    };
    let offset = match interval {
        AnalyticsInterval::Hour => i64::from(since.minute() * 60 + since.second()),
        AnalyticsInterval::Day => i64::from(since.num_seconds_from_midnight()),
        AnalyticsInterval::Week => {
            i64::from(since.weekday().num_days_from_monday()) * 86400
                + i64::from(since.num_seconds_from_midnight())
        }
    };
    // Integer nanoseconds preserve subsecond edges; the validated period is <=366 days.
    let span = (time.until - since).num_nanoseconds().unwrap_or(i64::MAX);
    let span = span + offset * 1_000_000_000 + i64::from(since.nanosecond());
    ((span - 1) / (seconds * 1_000_000_000) + 1) as usize
}

fn plan(request: &AnalyticsRequest) -> AppResult<Vec<ReadPlan>> {
    if !(1..=8).contains(&request.queries.len()) {
        return Err(invalid("Expected 1..8 named queries"));
    }
    let historical = request
        .queries
        .iter()
        .flat_map(|q| &q.measures)
        .any(|m| m.historical());
    if historical
        && request
            .queries
            .iter()
            .flat_map(|q| &q.measures)
            .any(|m| !m.historical())
    {
        return Err(invalid(
            "SQL and historical measures require separate batches",
        ));
    }
    let mut names = HashSet::new();
    let mut rows = 0;
    for q in &request.queries {
        if q.name.is_empty()
            || q.name.len() > 64
            || !q
                .name
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || c == b'_')
            || !names.insert(&q.name)
        {
            return Err(invalid(
                "Query names must be distinct ASCII identifiers of 1..64 characters",
            ));
        }
        let duration = q.time.until - q.time.since;
        if duration <= Duration::zero() || duration > Duration::days(366) {
            return Err(invalid(
                "Expected since < until and a period of at most 366 days",
            ));
        }
        if q.measures.is_empty()
            || q.measures.len() > 12
            || q.measures
                .iter()
                .collect::<std::collections::BTreeSet<_>>()
                .len()
                != q.measures.len()
        {
            return Err(invalid("Expected distinct consumption measures"));
        }
        if q.group_by.len() > 1 {
            return Err(invalid("Only one grouping is supported"));
        }
        let grouping = q.group_by.first();
        if q.measures
            .iter()
            .any(|m| m.reader() != q.measures[0].reader())
        {
            return Err(invalid(
                "Measures from different readers require separate named queries",
            ));
        }
        if q.measures[0].reader() != ReaderKind::Consumption {
            if !matches!(q.scope, AnalyticsScope::Personal { .. }) {
                return Err(AppError::Forbidden);
            }
            match q.measures[0].reader() {
                ReaderKind::Skills if grouping != Some(&AnalyticsGrouping::Skill) => {
                    return Err(invalid("Historical loads require skill grouping"));
                }
                ReaderKind::Turns
                    if !matches!(
                        grouping,
                        None | Some(AnalyticsGrouping::Agent | AnalyticsGrouping::Space)
                    ) =>
                {
                    return Err(invalid("Turns support total, agent or space grouping"));
                }
                ReaderKind::Turns
                    if grouping.is_some()
                        && q.measures.contains(&ConsumptionMeasure::AgentsUsed) =>
                {
                    return Err(invalid("Distinct agents require a total"));
                }
                ReaderKind::Conversations if grouping.is_some() => {
                    return Err(invalid("Retained conversations require a total"));
                }
                _ => {}
            }
        } else if matches!(
            grouping,
            Some(AnalyticsGrouping::Skill | AnalyticsGrouping::Space)
        ) {
            return Err(invalid("This grouping requires historical measures"));
        }
        if q.time.bucket.is_some() && grouping != Some(&AnalyticsGrouping::Time) {
            return Err(invalid("A bucket requires time grouping"));
        }
        let ranked = matches!(
            grouping,
            Some(
                AnalyticsGrouping::Agent
                    | AnalyticsGrouping::Model
                    | AnalyticsGrouping::Skill
                    | AnalyticsGrouping::Space
            )
        );
        if q.limit.is_some() && !ranked || !(1..=100).contains(&q.limit.unwrap_or(100)) {
            return Err(invalid("Only rankings accept a limit of 1..100"));
        }
        rows += if grouping == Some(&AnalyticsGrouping::Time) {
            let n = points(&q.time, interval(&q.time));
            if n > MAX_POINTS {
                return Err(too_large());
            }
            n
        } else if ranked {
            q.limit.unwrap_or(100)
        } else {
            1
        };
    }
    if rows > MAX_ROWS {
        return Err(too_large());
    }
    let mut plans: Vec<ReadPlan> = Vec::new();
    // Series first: a total/ranking shares any existing interval for that scope/period.
    // Two distinct requested series intervals need two reads, not a general optimizer.
    let indices = (0..request.queries.len())
        .filter(|&i| request.queries[i].group_by == [AnalyticsGrouping::Time])
        .chain(
            (0..request.queries.len())
                .filter(|&i| request.queries[i].group_by != [AnalyticsGrouping::Time]),
        );
    for i in indices {
        let q = &request.queries[i];
        let bucket = interval(&q.time);
        let compatible = plans.iter_mut().find(|p| {
            let other = &request.queries[p.query];
            other.measures[0].reader() == q.measures[0].reader()
                && other.scope == q.scope
                && other.time.since == q.time.since
                && other.time.until == q.time.until
                && (q.group_by != [AnalyticsGrouping::Time] || p.interval == bucket)
        });
        if let Some(p) = compatible {
            p.consumers.push(i);
            p.limit = p.limit.max(q.limit.unwrap_or(100));
        } else {
            plans.push(ReadPlan {
                query: i,
                interval: bucket,
                limit: q.limit.unwrap_or(100),
                consumers: vec![i],
            });
        }
    }
    Ok(plans)
}

async fn authorize_personal_organization(
    conn: &mut PgConnection,
    subject: &str,
    organization: uuid::Uuid,
) -> AppResult<()> {
    let facts = authorization::load_facts(&mut *conn, subject, organization).await?;
    if facts.space.kind != SpaceKind::Organization || !facts.in_organization {
        return Err(AppError::NotFound);
    }
    facts.require_active()?;
    if !authorization::can_work_in_organization(&mut *conn, subject, organization).await? {
        return Err(AppError::Forbidden);
    }
    Ok(())
}

async fn authorize<'a>(
    conn: &mut PgConnection,
    user: &'a CurrentUser,
    scope: &AnalyticsScope,
) -> AppResult<UsageScope<'a>> {
    match scope {
        AnalyticsScope::Personal { organization_id } => {
            authorize_personal_organization(&mut *conn, &user.uid, *organization_id).await?;
            Ok(UsageScope::Person {
                subject: &user.uid,
                organization: *organization_id,
            })
        }
        AnalyticsScope::Space { id } => {
            let facts = authorization::load_facts(&mut *conn, &user.uid, *id).await?;
            if !facts.in_organization {
                return Err(AppError::NotFound);
            }
            if !matches!(facts.space.kind, SpaceKind::Team | SpaceKind::Project) {
                return Err(invalid("team or project required"));
            }
            authorization::decide(&facts, SpacePermission::ReadUsage)?;
            Ok(UsageScope::Space {
                id: *id,
                team: facts.space.kind == SpaceKind::Team,
            })
        }
    }
}

async fn execute(
    state: &AppState,
    user: &CurrentUser,
    request: &AnalyticsRequest,
    plans: &[ReadPlan],
) -> AppResult<AnalyticsResponse> {
    if request.queries[0].measures[0].historical() {
        return history::execute(
            &state.pool,
            state.history.as_deref(),
            &user.uid,
            request,
            plans,
        )
        .await;
    }
    if request
        .queries
        .iter()
        .any(|q| matches!(q.scope, AnalyticsScope::Space { .. }))
    {
        onboarding::require_admitted(&state.pool, &state.auth, &user.uid).await?;
        if state.auth.enabled() {
            onboarding::require_accepted(
                &state.pool,
                state.onboarding.gcu_version.as_deref(),
                &user.uid,
            )
            .await?;
        }
    }
    let mut tx = state.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    sqlx::query("set local statement_timeout = '5s'")
        .execute(&mut *tx)
        .await?;
    sqlx::query("set local lock_timeout = '1s'")
        .execute(&mut *tx)
        .await?;
    let mut scopes = Vec::with_capacity(plans.len());
    // All scope decisions precede data reads, inside the same snapshot.
    for p in plans {
        scopes.push(authorize(&mut tx, user, &request.queries[p.query].scope).await?);
    }
    let mut results = BTreeMap::new();
    for (p, scope) in plans.iter().zip(&scopes) {
        let q = &request.queries[p.query];
        if q.measures[0] == ConsumptionMeasure::RetainedConversations {
            let value =
                read::retained_conversations(&mut tx, scope, q.time.since, q.time.until).await?;
            for &i in &p.consumers {
                let q = &request.queries[i];
                results.insert(
                    q.name.clone(),
                    AnalyticsResult {
                        since: q.time.since,
                        until: q.time.until,
                        timezone: q.time.timezone,
                        bucket: None,
                        measures: q.measures.iter().map(|m| m.metadata()).collect(),
                        rows: vec![AnalyticsRow {
                            dimensions: AnalyticsDimensions::Total,
                            values: BTreeMap::from([(
                                ConsumptionMeasure::RetainedConversations,
                                value.clone(),
                            )]),
                            estimates: BTreeMap::new(),
                        }],
                        truncated: false,
                    },
                );
            }
            continue;
        }
        let rows = read::read(
            &mut tx,
            scope,
            q.time.since,
            q.time.until,
            p.interval,
            p.limit,
        )
        .await?;
        for &i in &p.consumers {
            let q = &request.queries[i];
            results.insert(q.name.clone(), result(q, p.interval, &rows)?);
        }
    }
    tx.commit().await?;
    let response = AnalyticsResponse {
        calculation: {
            let mut measures = request.queries.iter().flat_map(|q| &q.measures);
            if measures.clone().all(|m| m.estimated()) {
                CalculationPrecision::Estimated
            } else if measures.any(|m| m.estimated()) {
                CalculationPrecision::Mixed
            } else {
                CalculationPrecision::Exact
            }
        },
        collection_completeness: CollectionCompleteness::Unknown,
        results,
    };
    if serde_json::to_vec(&response)
        .map_err(anyhow::Error::from)?
        .len()
        > MAX_RESPONSE_BYTES
    {
        return Err(too_large());
    }
    Ok(response)
}

fn result(
    q: &AnalyticsQuery,
    interval: AnalyticsInterval,
    source: &[AggregateRow],
) -> AppResult<AnalyticsResult> {
    let grouping = q.group_by.first();
    let mut rows = Vec::new();
    let mut truncated = false;
    for r in source {
        let dimensions = match (
            grouping,
            r.start,
            r.agent_instance_id,
            r.space_id,
            &r.model_source_id,
            &r.upstream_model_id,
        ) {
            (None, None, None, None, None, None) => AnalyticsDimensions::Total,
            (Some(AnalyticsGrouping::Time), Some(start), None, None, None, None) => {
                AnalyticsDimensions::Time { start }
            }
            (
                Some(AnalyticsGrouping::Agent),
                None,
                Some(agent_instance_id),
                Some(space_id),
                None,
                None,
            ) => AnalyticsDimensions::Agent {
                agent_instance_id,
                space_id,
                display_name: r.display_name.clone(),
            },
            (Some(AnalyticsGrouping::Model), None, None, None, Some(source), Some(model)) => {
                AnalyticsDimensions::Model {
                    model_source_id: source.clone(),
                    upstream_model_id: model.clone(),
                }
            }
            _ => continue,
        };
        if matches!(
            grouping,
            Some(
                AnalyticsGrouping::Agent
                    | AnalyticsGrouping::Model
                    | AnalyticsGrouping::Skill
                    | AnalyticsGrouping::Space
            )
        ) && rows.len() == q.limit.unwrap_or(100)
        {
            truncated = true;
            break;
        }
        let values = q
            .measures
            .iter()
            .filter(|m| !m.estimated())
            .map(|&m| {
                let value = match m {
                    ConsumptionMeasure::InputTokens => &r.input_tokens,
                    ConsumptionMeasure::OutputTokens => &r.output_tokens,
                    ConsumptionMeasure::CacheReadTokens => &r.cache_read_tokens,
                    ConsumptionMeasure::CacheCreationTokens => &r.cache_creation_tokens,
                    ConsumptionMeasure::TotalTokens => &r.total_tokens,
                    ConsumptionMeasure::RecordedExchanges => &r.recorded_exchanges,
                    _ => return Err(invalid("unsupported SQL counter")),
                };
                Ok((m, value.clone()))
            })
            .collect::<AppResult<_>>()?;
        let estimates = r
            .estimates
            .iter()
            .filter(|(m, _)| q.measures.contains(m))
            .map(|(m, v)| (*m, v.clone()))
            .collect();
        rows.push(AnalyticsRow {
            dimensions,
            values,
            estimates,
        });
    }
    if grouping.is_none() && rows.len() != 1 {
        return Err(anyhow::anyhow!("missing consumption total").into());
    }
    Ok(AnalyticsResult {
        since: q.time.since,
        until: q.time.until,
        timezone: q.time.timezone,
        bucket: (grouping == Some(&AnalyticsGrouping::Time)).then_some(interval),
        measures: q.measures.iter().map(|&id| id.metadata()).collect(),
        rows,
        truncated,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{Value, json};

    fn query(name: &str, grouping: Vec<&str>) -> Value {
        json!({"name":name,"scope":{"kind":"self","organization_id":"00000000-0000-0000-0000-000000000001"},"time":{"since":"2026-01-01T00:00:00Z","until":"2026-01-03T00:00:00Z","timezone":"UTC"},"measures":["usage.input_tokens"],"group_by":grouping})
    }

    #[test]
    fn activity_plans_share_turn_reads_but_never_change_consumption_semantics() {
        let mut total = query("total", vec![]);
        total["measures"] = json!(["activity.completed_turns", "activity.agents_used"]);
        let mut agents = query("agents", vec!["agent"]);
        agents["measures"] = json!(["activity.completed_turns"]);
        let mut spaces = agents.clone();
        spaces["name"] = json!("spaces");
        spaces["group_by"] = json!(["space"]);
        let request: AnalyticsRequest =
            serde_json::from_value(json!({"queries":[total.clone(),agents.clone(),spaces]}))
                .unwrap();
        let plans = plan(&request).unwrap();
        assert_eq!(plans.len(), 1);
        assert_eq!(plans[0].consumers.len(), 3);
        for (measure, grouping) in [
            ("activity.retained_conversations", "agent"),
            ("activity.agents_used", "agent"),
            ("usage.total_tokens", "space"),
            ("activity.completed_turns", "time"),
        ] {
            agents["measures"] = json!([measure]);
            agents["group_by"] = json!([grouping]);
            let request: AnalyticsRequest =
                serde_json::from_value(json!({"queries":[agents.clone()]})).unwrap();
            assert!(plan(&request).is_err());
        }
        total["measures"] = json!(["activity.completed_turns", "usage.recorded_exchanges"]);
        let request = serde_json::from_value(json!({"queries":[total]})).unwrap();
        assert!(plan(&request).is_err());
    }

    #[test]
    fn compatible_results_share_one_read_even_with_explicit_series_interval() {
        let mut series = query("series", vec!["time"]);
        series["time"]["bucket"] = json!("day");
        let mut agent = query("agent", vec!["agent"]);
        agent["limit"] = json!(3);
        let mut request: AnalyticsRequest = serde_json::from_value(
            json!({"queries":[query("total", vec![]),series,agent,query("model",vec!["model"])]}),
        )
        .unwrap();
        let reads = plan(&request).unwrap();
        assert_eq!(reads.len(), 1);
        assert_eq!(reads[0].consumers.len(), 4);
        assert_eq!(reads[0].interval, AnalyticsInterval::Day);
        assert_eq!(reads[0].limit, 100);
        request.queries[3].time.until += Duration::seconds(1);
        assert_eq!(plan(&request).unwrap().len(), 2);
        request.queries[2].scope = AnalyticsScope::Space {
            id: uuid::Uuid::new_v4(),
        };
        assert_eq!(plan(&request).unwrap().len(), 3);
    }

    #[test]
    fn bounds_include_partial_buckets_and_reject_excess_work() {
        let mut q: AnalyticsQuery = serde_json::from_value(query("series", vec!["time"])).unwrap();
        assert_eq!(points(&q.time, AnalyticsInterval::Hour), 48);
        q.time.since -= Duration::nanoseconds(1);
        assert_eq!(points(&q.time, AnalyticsInterval::Hour), 49);
        q.time.until = q.time.since + Duration::days(366);
        q.time.bucket = Some(AnalyticsInterval::Hour);
        assert!(plan(&AnalyticsRequest { queries: vec![q] }).is_err());
        for (hours, bucket) in [
            (48, AnalyticsInterval::Hour),
            (49, AnalyticsInterval::Day),
            (92 * 24, AnalyticsInterval::Day),
            (92 * 24 + 1, AnalyticsInterval::Week),
        ] {
            let mut q: AnalyticsQuery =
                serde_json::from_value(query("series", vec!["time"])).unwrap();
            q.time.until = q.time.since + Duration::hours(hours);
            assert_eq!(interval(&q.time), bucket);
        }
    }
}
