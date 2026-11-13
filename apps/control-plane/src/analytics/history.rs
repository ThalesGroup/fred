// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Historical read port. Only validated self observations reach this boundary.
//! No engine client, DSL, index name or raw response belongs to this service.
use super::models::*;
use crate::error::{AppError, AppResult};
use chrono::{DateTime, Utc};
use futures::future::BoxFuture;
use std::collections::BTreeMap;

pub struct ReadScope<'a> {
    pub subject: &'a str,
    pub spaces: &'a [uuid::Uuid],
    pub since: DateTime<Utc>,
    pub until: DateTime<Utc>,
    pub limit: usize,
}

pub struct SkillLoads {
    pub name: String,
    pub user: u64,
    pub agent: u64,
}

pub struct SkillResult {
    pub rows: Vec<SkillLoads>,
    pub truncated: bool,
}

/// Complete bounded set, before any public ranking limit.
pub struct TurnCount {
    pub space_id: uuid::Uuid,
    pub agent_instance_id: uuid::Uuid,
    pub display_name: Option<String>,
    pub latest: DateTime<Utc>,
    pub count: u64,
}

#[derive(Debug, thiserror::Error)]
pub enum ReadError {
    #[error("Historical source unavailable or incompatible")]
    Unavailable,
    #[error("Historical aggregation exceeds the bounded read budget")]
    TooLarge,
}

pub trait Reader: Send + Sync {
    fn skill_loads<'a>(
        &'a self,
        query: ReadScope<'a>,
    ) -> BoxFuture<'a, Result<SkillResult, ReadError>>;
    fn completed_turns<'a>(
        &'a self,
        query: ReadScope<'a>,
    ) -> BoxFuture<'a, Result<Vec<TurnCount>, ReadError>>;
}

pub(super) async fn execute(
    pool: &sqlx::PgPool,
    reader: Option<&dyn Reader>,
    subject: &str,
    request: &AnalyticsRequest,
    plans: &[super::ReadPlan],
) -> AppResult<AnalyticsResponse> {
    // Resolve and authorize the complete batch before any external read, then release SQL.
    let mut scopes = Vec::with_capacity(plans.len());
    let mut tx = pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    sqlx::query("set local statement_timeout = '5s'")
        .execute(&mut *tx)
        .await?;
    for plan in plans {
        let q = &request.queries[plan.query];
        let AnalyticsScope::Personal { organization_id } = q.scope else {
            return Err(AppError::Forbidden);
        };
        super::authorize_personal_organization(&mut tx, subject, organization_id).await?;
        let spaces: Vec<uuid::Uuid> = sqlx::query_scalar(concat!(
            crate::sessions::usage::read::organization_spaces!("$1"),
            " limit 50001"
        ))
        .bind(organization_id)
        .fetch_all(&mut *tx)
        .await?;
        if spaces.is_empty() || spaces.len() > 50000 {
            return Err(super::too_large());
        }
        scopes.push(spaces);
    }
    // The same current-membership reader as /me/spaces. It is not an authority
    // substitute: every organization above was authorized independently.
    let memberships = if request
        .queries
        .iter()
        .any(|q| q.group_by == [AnalyticsGrouping::Space])
    {
        crate::authorization::memberships(&mut *tx, subject).await?
    } else {
        Vec::new()
    };
    tx.commit().await?;
    let reader = reader
        .ok_or_else(|| AppError::Unavailable("Historical source is not configured".into()))?;
    let mut results = BTreeMap::new();
    for (plan, spaces) in plans.iter().zip(&scopes) {
        let q = &request.queries[plan.query];
        if q.measures[0].reader() == ReaderKind::Turns {
            let data = reader
                .completed_turns(ReadScope {
                    subject,
                    spaces,
                    since: q.time.since,
                    until: q.time.until,
                    limit: plan.limit,
                })
                .await
                .map_err(read_error)?;
            let AnalyticsScope::Personal { organization_id } = q.scope else {
                return Err(AppError::Forbidden);
            };
            let member_spaces: Vec<_> = memberships
                .iter()
                .filter(|(space, _)| {
                    space.organization_id == organization_id
                        && space.kind != crate::domain::SpaceKind::Organization
                })
                .map(|(space, _)| space.id)
                .collect();
            for &i in &plan.consumers {
                let q = &request.queries[i];
                results.insert(q.name.clone(), turn_result(q, &data, &member_spaces)?);
            }
            continue;
        }
        let data = reader
            .skill_loads(ReadScope {
                subject,
                spaces,
                since: q.time.since,
                until: q.time.until,
                limit: plan.limit,
            })
            .await
            .map_err(read_error)?;
        for &i in &plan.consumers {
            let q = &request.queries[i];
            results.insert(
                q.name.clone(),
                AnalyticsResult {
                    since: q.time.since,
                    until: q.time.until,
                    timezone: q.time.timezone,
                    bucket: None,
                    measures: q.measures.iter().map(|m| m.metadata()).collect(),
                    truncated: data.truncated || data.rows.len() > q.limit.unwrap_or(100),
                    rows: data
                        .rows
                        .iter()
                        .take(q.limit.unwrap_or(100))
                        .map(|r| {
                            let total = r.user.checked_add(r.agent).ok_or_else(super::too_large)?;
                            Ok(AnalyticsRow {
                                dimensions: AnalyticsDimensions::Skill {
                                    name: r.name.clone(),
                                },
                                values: q
                                    .measures
                                    .iter()
                                    .map(|&m| {
                                        (
                                            m,
                                            match m {
                                                ConsumptionMeasure::UserSkillLoads => r.user,
                                                ConsumptionMeasure::AgentSkillLoads => r.agent,
                                                _ => total,
                                            }
                                            .to_string(),
                                        )
                                    })
                                    .collect(),
                                estimates: BTreeMap::new(),
                            })
                        })
                        .collect::<AppResult<_>>()?,
                },
            );
        }
    }
    let response = AnalyticsResponse {
        calculation: CalculationPrecision::Exact,
        collection_completeness: CollectionCompleteness::Unknown,
        results,
    };
    if serde_json::to_vec(&response)
        .map_err(anyhow::Error::from)?
        .len()
        > super::MAX_RESPONSE_BYTES
    {
        return Err(super::too_large());
    }
    Ok(response)
}

fn read_error(error: ReadError) -> AppError {
    match error {
        ReadError::Unavailable => AppError::Unavailable(error.to_string()),
        ReadError::TooLarge => super::too_large(),
    }
}

fn turn_result(
    q: &AnalyticsQuery,
    data: &[TurnCount],
    member_spaces: &[uuid::Uuid],
) -> AppResult<AnalyticsResult> {
    let mut agents = BTreeMap::<uuid::Uuid, (&TurnCount, u128)>::new();
    let mut spaces: BTreeMap<_, u128> = member_spaces.iter().map(|id| (*id, 0)).collect();
    let mut total = 0u128;
    for row in data {
        let count = u128::from(row.count);
        total += count;
        let agent = agents.entry(row.agent_instance_id).or_insert((row, 0));
        agent.1 += count;
        if (row.latest, row.space_id) > (agent.0.latest, agent.0.space_id) {
            agent.0 = row;
        }
        if let Some(value) = spaces.get_mut(&row.space_id) {
            *value += count;
        }
    }
    let mut ranked: Vec<(AnalyticsDimensions, u128)> = match q.group_by.first() {
        None => vec![],
        Some(AnalyticsGrouping::Agent) => agents
            .iter()
            .map(|(id, (row, count))| {
                (
                    AnalyticsDimensions::Agent {
                        agent_instance_id: *id,
                        space_id: row.space_id,
                        display_name: row.display_name.clone(),
                    },
                    *count,
                )
            })
            .collect(),
        Some(AnalyticsGrouping::Space) => spaces
            .into_iter()
            .map(|(id, count)| (AnalyticsDimensions::Space { space_id: id }, count))
            .collect(),
        _ => return Err(super::invalid("unsupported turn grouping")),
    };
    // Stable identity ordering comes from BTreeMap; stable sort preserves it for ties.
    ranked.sort_by_key(|row| std::cmp::Reverse(row.1));
    let truncated = ranked.len() > q.limit.unwrap_or(100);
    ranked.truncate(q.limit.unwrap_or(100));
    let rows = if q.group_by.is_empty() {
        vec![AnalyticsRow {
            dimensions: AnalyticsDimensions::Total,
            values: q
                .measures
                .iter()
                .map(|&m| {
                    Ok((
                        m,
                        match m {
                            ConsumptionMeasure::CompletedTurns => total.to_string(),
                            ConsumptionMeasure::AgentsUsed => agents.len().to_string(),
                            _ => return Err(super::invalid("unsupported turn measure")),
                        },
                    ))
                })
                .collect::<AppResult<_>>()?,
            estimates: BTreeMap::new(),
        }]
    } else {
        ranked
            .into_iter()
            .map(|(dimensions, count)| AnalyticsRow {
                dimensions,
                values: BTreeMap::from([(ConsumptionMeasure::CompletedTurns, count.to_string())]),
                estimates: BTreeMap::new(),
            })
            .collect()
    };
    Ok(AnalyticsResult {
        since: q.time.since,
        until: q.time.until,
        timezone: q.time.timezone,
        bucket: None,
        measures: q.measures.iter().map(|m| m.metadata()).collect(),
        rows,
        truncated,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use uuid::Uuid;

    #[test]
    fn exact_distinct_agents_and_membership_rankings_precede_limits() {
        let a = Uuid::from_u128(1);
        let b = Uuid::from_u128(2);
        let left = Uuid::from_u128(11);
        let right = Uuid::from_u128(12);
        let zero = Uuid::from_u128(13);
        let latest = "2026-01-02T00:00:00Z".parse().unwrap();
        let rows = vec![
            TurnCount {
                space_id: left,
                agent_instance_id: a,
                display_name: Some("Same name".into()),
                latest,
                count: 9_007_199_254_740_993,
            },
            TurnCount {
                space_id: right,
                agent_instance_id: a,
                display_name: Some("Same name".into()),
                latest,
                count: 7,
            },
            TurnCount {
                space_id: right,
                agent_instance_id: b,
                display_name: Some("Same name".into()),
                latest,
                count: 7,
            },
        ];
        let mut q: AnalyticsQuery = serde_json::from_value(json!({
            "name":"total", "scope":{"kind":"self","organization_id":a},
            "time":{"since":"2026-01-01T00:00:00Z","until":"2026-01-03T00:00:00Z","timezone":"UTC"},
            "measures":["activity.completed_turns","activity.agents_used"]
        }))
        .unwrap();
        let total = turn_result(&q, &rows, &[right, zero]).unwrap();
        assert_eq!(
            total.rows[0].values[&ConsumptionMeasure::CompletedTurns],
            "9007199254741007"
        );
        assert_eq!(total.rows[0].values[&ConsumptionMeasure::AgentsUsed], "2");
        q.measures = vec![ConsumptionMeasure::CompletedTurns];
        q.group_by = vec![AnalyticsGrouping::Agent];
        q.limit = Some(1);
        let ranked = turn_result(&q, &rows, &[right, zero]).unwrap();
        assert!(ranked.truncated);
        assert_eq!(
            ranked.rows[0].values[&ConsumptionMeasure::CompletedTurns],
            "9007199254741000"
        );
        q.group_by = vec![AnalyticsGrouping::Space];
        let teams = turn_result(&q, &rows, &[right, zero]).unwrap();
        assert!(teams.truncated);
        assert!(
            matches!(teams.rows[0].dimensions, AnalyticsDimensions::Space { space_id } if space_id == right)
        );
        assert_eq!(
            teams.rows[0].values[&ConsumptionMeasure::CompletedTurns],
            "14"
        );
        q.limit = Some(5);
        let empty = turn_result(&q, &[], &[right, zero]).unwrap();
        assert_eq!(empty.rows.len(), 2);
        assert!(
            matches!(empty.rows[0].dimensions, AnalyticsDimensions::Space { space_id } if space_id == right)
        );
        assert_eq!(
            empty.rows[1].values[&ConsumptionMeasure::CompletedTurns],
            "0"
        );
        assert!(turn_result(&q, &rows, &[]).unwrap().rows.is_empty());
    }
}
