// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Organization-owner technical aggregates. No content or physical storage reads.
mod models;
mod store;

use std::collections::{BTreeMap, BTreeSet};

use axum::{Json, extract::State};
use chrono::Utc;
use serde::Deserialize;
use utoipa_axum::{router::OpenApiRouter, routes};
use uuid::Uuid;

use crate::{
    api::AppState,
    domain::{Role, SpaceKind},
    error::{AppError, AppResult, ErrorBody},
    extract::{ApiPath, ApiQuery},
    onboarding::AdmittedUser,
    processing::models::ProcessingStatus,
    roles::SpacePermission,
    spaces,
};
use models::*;

pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(organization_supervision))
        .routes(routes!(team_supervision))
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Page {
    after: Option<Uuid>,
}

#[utoipa::path(
    get, path = "/organizations/{organization_id}/supervision",
    params(("organization_id" = Uuid, Path), ("after" = Option<Uuid>, Query,
        description = "Exclusive team UUID cursor; does not filter organization totals")),
    responses(
        (status = 200, body = OrganizationSupervision),
        (status = 401, body = ErrorBody), (status = 403, body = ErrorBody),
        (status = 404, body = ErrorBody), (status = 409, body = ErrorBody),
        (status = 422, body = ErrorBody), (status = 503, body = ErrorBody),
        (status = 500, body = ErrorBody)
    )
)]
async fn organization_supervision(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(organization_id): ApiPath<Uuid>,
    ApiQuery(page): ApiQuery<Page>,
) -> AppResult<Json<OrganizationSupervision>> {
    let collection_started_at = Utc::now();
    authorize(&s, &user.uid, organization_id).await?;
    let snapshot = store::load(&s.pool, organization_id, None, page.after).await?;
    let active_teams = snapshot
        .scopes
        .iter()
        .filter(|s| s.active && s.kind == SpaceKind::Team)
        .count() as u64;
    let (mut counts, mut teams) = collect(&s, snapshot).await?;
    let next_cursor = if teams.len() > 100 {
        teams.truncate(100);
        teams.last().map(|team| team.id)
    } else {
        None
    };
    Ok(Json(OrganizationSupervision {
        organization_id,
        collection_started_at,
        collection_finished_at: Utc::now(),
        active_teams,
        totals: take(&mut counts, Bucket::Total),
        organization_direct: take(&mut counts, Bucket::Organization),
        teams_total: take(&mut counts, Bucket::Teams),
        personal_total: take(&mut counts, Bucket::Personal),
        teams: SupervisionTeamsPage {
            items: teams,
            next_cursor,
        },
    }))
}

#[utoipa::path(
    get, path = "/organizations/{organization_id}/supervision/teams/{team_id}",
    params(("organization_id" = Uuid, Path), ("team_id" = Uuid, Path)),
    responses(
        (status = 200, body = TeamSupervisionDetail),
        (status = 401, body = ErrorBody), (status = 403, body = ErrorBody),
        (status = 404, body = ErrorBody), (status = 409, body = ErrorBody),
        (status = 422, body = ErrorBody), (status = 503, body = ErrorBody),
        (status = 500, body = ErrorBody)
    )
)]
async fn team_supervision(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((organization_id, team_id)): ApiPath<(Uuid, Uuid)>,
) -> AppResult<Json<TeamSupervisionDetail>> {
    let collection_started_at = Utc::now();
    authorize(&s, &user.uid, organization_id).await?;
    let snapshot = store::load(&s.pool, organization_id, Some(team_id), None).await?;
    let (_, mut teams) = collect(&s, snapshot).await?;
    let team = teams.pop().ok_or(AppError::NotFound)?;
    Ok(Json(TeamSupervisionDetail {
        organization_id,
        collection_started_at,
        collection_finished_at: Utc::now(),
        team,
    }))
}

async fn authorize(s: &AppState, user: &str, id: Uuid) -> AppResult<()> {
    let organization = spaces::load(&s.pool, id).await?;
    if organization.kind != SpaceKind::Organization {
        return Err(AppError::NotFound);
    }
    let inside = spaces::in_organization(&s.pool, &s.fga, user, id)
        .await
        .map_err(|error| match error {
            AppError::Internal(_) => unavailable(),
            other => other,
        })?;
    if !inside {
        return Err(AppError::NotFound);
    }
    crate::lifecycle::store::require_active(&s.pool, id).await?;
    if !s
        .fga
        .check_space(user, SpacePermission::OwnOrganization, id)
        .await
        .map_err(|_| unavailable())?
    {
        return Err(AppError::Forbidden);
    }
    Ok(())
}

fn unavailable() -> AppError {
    tracing::warn!("organization supervision authorization dependency unavailable");
    AppError::Unavailable("Authorization service temporarily unavailable".into())
}

#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
enum Bucket {
    Total,
    Organization,
    Teams,
    Personal,
    Team(Uuid),
}

#[derive(Default)]
struct Accumulator {
    counts: SupervisionCounts,
    users: BTreeSet<String>,
    roles: BTreeMap<Role, u64>,
}

impl Accumulator {
    fn add_counts(&mut self, row: &store::Counts) -> AppResult<()> {
        let c = &mut self.counts;
        for (value, additional) in [
            (&mut c.active.documents, row.documents),
            (&mut c.active.bytes, row.bytes),
            (&mut c.pending_purge.documents, row.purge_documents),
            (&mut c.pending_purge.bytes, row.purge_bytes),
            (&mut c.published.documents, row.published_documents),
            (&mut c.published.chunks, row.chunks),
            (&mut c.published.vectors, row.vectors),
            (&mut c.published.tabular_datasets, row.datasets),
            (&mut c.published.known_rows, row.known_rows),
            (
                &mut c.published.datasets_with_unknown_rows,
                row.unknown_datasets,
            ),
        ] {
            *value = value
                .checked_add(additional)
                .ok_or_else(|| AppError::Internal(anyhow::anyhow!("supervision count overflow")))?;
        }
        Ok(())
    }

    fn add_processing(&mut self, row: &store::Processing) -> AppResult<()> {
        let value = if row.status == ProcessingStatus::Failed {
            &mut self.counts.failed_documents
        } else {
            let counts = &mut self.counts.processing;
            let index = match counts
                .iter()
                .position(|c| c.status == row.status && c.stage == row.stage)
            {
                Some(index) => index,
                None => {
                    counts.push(ProcessingCount {
                        status: row.status,
                        stage: row.stage,
                        documents: 0,
                    });
                    counts.len() - 1
                }
            };
            &mut counts[index].documents
        };
        *value = value
            .checked_add(row.documents)
            .ok_or_else(|| AppError::Internal(anyhow::anyhow!("supervision count overflow")))?;
        Ok(())
    }

    fn finish(mut self) -> SupervisionCounts {
        self.counts.distinct_users = self.users.len() as u64;
        self.counts.direct_roles = self
            .roles
            .into_iter()
            .map(|(role, assignments)| RoleAssignments { role, assignments })
            .collect();
        self.counts.published.total_rows = (self.counts.published.datasets_with_unknown_rows == 0)
            .then_some(self.counts.published.known_rows);
        self.counts
            .processing
            .sort_by_key(|c| (c.status == ProcessingStatus::Running, c.stage.ordinal()));
        self.counts
    }
}

fn take(counts: &mut BTreeMap<Bucket, Accumulator>, bucket: Bucket) -> SupervisionCounts {
    counts.remove(&bucket).unwrap_or_default().finish()
}

async fn collect(
    s: &AppState,
    snapshot: store::Snapshot,
) -> AppResult<(BTreeMap<Bucket, Accumulator>, Vec<TeamSupervision>)> {
    let mut destinations = BTreeMap::new();
    let page: BTreeSet<_> = snapshot.teams.iter().map(|team| team.id).collect();
    for scope in &snapshot.scopes {
        let mut buckets = vec![Bucket::Total];
        let team = match scope.kind {
            SpaceKind::Organization => {
                buckets.push(Bucket::Organization);
                None
            }
            SpaceKind::Personal => {
                buckets.push(Bucket::Personal);
                None
            }
            SpaceKind::Team => {
                buckets.push(Bucket::Teams);
                Some(scope.id)
            }
            SpaceKind::Project => {
                buckets.push(Bucket::Teams);
                scope.parent_id
            }
        };
        if let Some(id) = team.filter(|id| page.contains(id)) {
            buckets.push(Bucket::Team(id));
        }
        destinations.insert(scope.id, buckets);
    }
    let mut counts: BTreeMap<Bucket, Accumulator> = BTreeMap::new();
    for row in &snapshot.counts {
        let buckets = destinations
            .get(&row.space_id)
            .ok_or_else(|| AppError::Internal(anyhow::anyhow!("missing supervision scope")))?;
        for bucket in buckets {
            counts.entry(*bucket).or_default().add_counts(row)?;
        }
    }
    for row in &snapshot.processing {
        let buckets = destinations
            .get(&row.space_id)
            .ok_or_else(|| AppError::Internal(anyhow::anyhow!("missing supervision scope")))?;
        for bucket in buckets {
            counts.entry(*bucket).or_default().add_processing(row)?;
        }
    }
    let active: Vec<_> = snapshot
        .scopes
        .iter()
        .filter(|s| s.active)
        .map(|s| s.id)
        .collect();
    let grants = s.fga.grants_on(&active).await.map_err(|_| unavailable())?;
    for (id, grants) in grants {
        let buckets = destinations
            .get(&id)
            .ok_or_else(|| AppError::Internal(anyhow::anyhow!("missing supervision scope")))?;
        // A repeated tuple across pages cannot inflate an attribution count.
        for (user, role) in grants.into_iter().collect::<BTreeSet<_>>() {
            for bucket in buckets {
                let total = counts.entry(*bucket).or_default();
                total.users.insert(user.clone());
                *total.roles.entry(role).or_default() += 1;
            }
        }
    }
    let teams = snapshot
        .teams
        .into_iter()
        .map(|team| TeamSupervision {
            id: team.id,
            name: team.name,
            counts: take(&mut counts, Bucket::Team(team.id)),
        })
        .collect();
    Ok((counts, teams))
}
