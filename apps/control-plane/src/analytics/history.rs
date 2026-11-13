// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Historical read port. Only validated self skill loads reach this boundary.
//! No engine client, DSL, index name or raw response belongs to this service.
use super::models::*;
use crate::error::{AppError, AppResult};
use chrono::{DateTime, Utc};
use futures::future::BoxFuture;
use std::collections::BTreeMap;

pub struct SkillRead<'a> {
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
        query: SkillRead<'a>,
    ) -> BoxFuture<'a, Result<SkillResult, ReadError>>;
}

pub(super) async fn execute(
    pool: &sqlx::PgPool,
    reader: Option<&dyn Reader>,
    subject: &str,
    request: &AnalyticsRequest,
) -> AppResult<AnalyticsResponse> {
    // Resolve and authorize the complete batch before any external read, then release SQL.
    let mut scopes = Vec::with_capacity(request.queries.len());
    let mut tx = pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    sqlx::query("set local statement_timeout = '5s'")
        .execute(&mut *tx)
        .await?;
    for q in &request.queries {
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
    tx.commit().await?;
    let reader = reader
        .ok_or_else(|| AppError::Unavailable("Historical source is not configured".into()))?;
    let mut results = BTreeMap::new();
    for (q, spaces) in request.queries.iter().zip(&scopes) {
        let data = reader
            .skill_loads(SkillRead {
                subject,
                spaces,
                since: q.time.since,
                until: q.time.until,
                limit: q.limit.unwrap_or(100),
            })
            .await
            .map_err(|e| match e {
                ReadError::Unavailable => AppError::Unavailable(e.to_string()),
                ReadError::TooLarge => super::too_large(),
            })?;
        results.insert(
            q.name.clone(),
            AnalyticsResult {
                since: q.time.since,
                until: q.time.until,
                timezone: q.time.timezone,
                bucket: None,
                measures: q.measures.iter().map(|m| m.metadata()).collect(),
                truncated: data.truncated,
                rows: data
                    .rows
                    .into_iter()
                    .map(|r| {
                        let total = r.user.checked_add(r.agent).ok_or_else(super::too_large)?;
                        Ok(AnalyticsRow {
                            dimensions: AnalyticsDimensions::Skill { name: r.name },
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
