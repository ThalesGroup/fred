// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Organization home presentation. Every launcher retains ordinary space permissions.
use crate::{
    api::AppState,
    authorization::{self, subject_spaces},
    domain::{Permission, SpaceKind},
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath, ApiQuery},
    onboarding::AdmittedUser,
    roles::SpacePermission,
};
use axum::{Json, extract::State, http::StatusCode};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use utoipa::ToSchema;
use uuid::Uuid;

#[derive(Clone, Default, Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum HomeLayout {
    #[default]
    Classic,
    Advanced,
}
impl HomeLayout {
    fn as_str(&self) -> &'static str {
        match self {
            Self::Classic => "classic",
            Self::Advanced => "advanced",
        }
    }
}
#[derive(Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct FeaturedAgentEntry {
    pub agent_instance_id: Uuid,
    pub badge: Option<String>,
    pub highlights: Vec<String>,
}
#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SetOrganizationHomeRequest {
    pub layout: HomeLayout,
    #[schema(max_items = 10)]
    pub featured: Vec<FeaturedAgentEntry>,
    pub ask_agent_instance_id: Option<Uuid>,
}
#[derive(Clone, Serialize, ToSchema, sqlx::FromRow)]
pub struct HomeAgent {
    pub template_id: Uuid,
    pub agent_instance_id: Uuid,
    pub space_id: Uuid,
    pub space_name: String,
    pub display_name: String,
    pub role: String,
    pub description: Option<String>,
}
#[derive(Serialize, ToSchema)]
pub struct FeaturedHomeAgent {
    pub agent: HomeAgent,
    pub badge: Option<String>,
    pub highlights: Vec<String>,
}
#[derive(Serialize, ToSchema)]
pub struct AdminHomeAgent {
    pub agent_instance_id: Uuid,
    /// Absent when the current manager can no longer read/use this agent.
    pub agent: Option<HomeAgent>,
    pub badge: Option<String>,
    pub highlights: Vec<String>,
}
#[derive(Serialize, ToSchema)]
pub struct OrganizationHomeSettings {
    pub layout: HomeLayout,
    pub featured: Vec<AdminHomeAgent>,
    pub ask_agent: Option<AdminHomeAgent>,
    pub updated_by: Option<String>,
    pub updated_at: Option<DateTime<Utc>>,
}
#[derive(Serialize, ToSchema)]
pub struct HomeShowcase {
    pub recent_agents: Vec<HomeAgent>,
    pub layout: HomeLayout,
    pub featured: Vec<FeaturedHomeAgent>,
    pub ask_agent: Option<HomeAgent>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PageQuery {
    after: Option<Uuid>,
}
#[derive(Serialize, ToSchema)]
pub struct HomeAgentPage {
    pub items: Vec<HomeAgent>,
    #[schema(required = true)]
    pub next_cursor: Option<Uuid>,
}
#[derive(sqlx::FromRow)]
struct StoredEntry {
    position: i16,
    agent_instance_id: Uuid,
    badge: Option<String>,
    highlights: Vec<String>,
}

pub(crate) fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new()
        .routes(utoipa_axum::routes!(
            organization_home_settings,
            set_organization_home
        ))
        .routes(utoipa_axum::routes!(organization_home_candidates))
        .routes(utoipa_axum::routes!(organization_home))
}
async fn available<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    s: &AppState,
    subject: &str,
    organization: Uuid,
    ids: Option<&[Uuid]>,
    after: Option<Uuid>,
    recent: bool,
) -> AppResult<Vec<HomeAgent>> {
    let mut runtimes: Vec<&str> = s
        .agent_catalog
        .runtime_catalog_sources
        .iter()
        .filter(|r| r.enabled)
        .map(|r| r.runtime_id.as_str())
        .collect();
    runtimes.push(fred_rust_agent::DEFINITION.provider);
    Ok(sqlx::query_as(concat!(subject_spaces!(), "select a.template_id,a.agent_instance_id,a.space_id,s.name as space_name,a.display_name,a.description,
        coalesce(a.tuning->>'role','') as role
        from agent_instance a join subject_spaces s on s.id=a.space_id
        join agent_template_policy policy on policy.template_id=a.template_id and policy.organization_id=s.organization_id
        where s.organization_id=$3 and s.active and (s.kind in ('team','project') or ($8 and s.kind='personal' and exists(select 1 from organization_participants p where p.organization_id=s.organization_id))) and s.direct_roles && $4::text[]
        and a.enabled and a.preparation_state='ready' and a.source_runtime_id=any($5)
        and ($6::uuid[] is null or a.agent_instance_id=any($6)) and a.agent_instance_id > $7
        order by case when $8 then (select max(sm.updated_at) from session_metadata sm where sm.space_id=a.space_id and sm.user_id=$1 and sm.agent_instance_id=a.agent_instance_id and sm.deletion_id is null) end desc nulls last,a.agent_instance_id limit case when $8 then 5 else 101 end"))
        .bind(subject).bind(authorization::roles_granting(SpacePermission::CreatePersonalSpace)).bind(organization)
        .bind(authorization::roles_granting(SpacePermission::Read)).bind(runtimes).bind(ids).bind(after.unwrap_or(Uuid::nil())).bind(recent)
        .fetch_all(ex).await?)
}
async fn settings<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    organization: Uuid,
) -> AppResult<(HomeLayout, Option<String>, Option<DateTime<Utc>>)> {
    let row: Option<(String,String,DateTime<Utc>)> = sqlx::query_as("select layout,updated_by,updated_at from organization_home_settings where organization_id=$1").bind(organization).fetch_optional(ex).await?;
    Ok(match row {
        Some((layout, by, at)) => (
            if layout == "advanced" {
                HomeLayout::Advanced
            } else {
                HomeLayout::Classic
            },
            Some(by),
            Some(at),
        ),
        None => (HomeLayout::Classic, None, None),
    })
}
async fn entries<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    organization: Uuid,
) -> AppResult<Vec<StoredEntry>> {
    Ok(sqlx::query_as("select position,agent_instance_id,badge,highlights from organization_home_agent where organization_id=$1 order by position").bind(organization).fetch_all(ex).await?)
}
async fn owner<'e>(ex: impl sqlx::PgExecutor<'e>, subject: &str, id: Uuid) -> AppResult<()> {
    authorization::authorize_organization(ex, subject, id, Permission::Manage).await?;
    Ok(())
}

#[utoipa::path(get,path="/spaces/{organization_id}/home-settings",params(("organization_id"=Uuid,Path)),responses((status=200,body=OrganizationHomeSettings),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody)))]
async fn organization_home_settings(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<Json<OrganizationHomeSettings>> {
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read read only")
        .execute(&mut *tx)
        .await?;
    owner(&mut *tx, &user.uid, id).await?;
    let (layout, updated_by, updated_at) = settings(&mut *tx, id).await?;
    let saved = entries(&mut *tx, id).await?;
    let ids: Vec<_> = saved.iter().map(|e| e.agent_instance_id).collect();
    let visible = available(&mut *tx, &s, &user.uid, id, Some(&ids), None, false).await?;
    let mut featured = vec![];
    let mut ask_agent = None;
    for e in saved {
        let row = AdminHomeAgent {
            agent: visible
                .iter()
                .find(|a| a.agent_instance_id == e.agent_instance_id)
                .cloned(),
            agent_instance_id: e.agent_instance_id,
            badge: e.badge,
            highlights: e.highlights,
        };
        if e.position == -1 {
            ask_agent = Some(row)
        } else {
            featured.push(row)
        }
    }
    tx.commit().await?;
    Ok(Json(OrganizationHomeSettings {
        layout,
        featured,
        ask_agent,
        updated_by,
        updated_at,
    }))
}
#[utoipa::path(get,path="/spaces/{organization_id}/home-candidates",params(("organization_id"=Uuid,Path),("after"=Option<Uuid>,Query)),responses((status=200,body=HomeAgentPage),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody)))]
async fn organization_home_candidates(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    ApiQuery(query): ApiQuery<PageQuery>,
) -> AppResult<Json<HomeAgentPage>> {
    owner(&s.pool, &user.uid, id).await?;
    let mut items = available(&s.pool, &s, &user.uid, id, None, query.after, false).await?;
    let next_cursor = (items.len() > 100).then(|| items[99].agent_instance_id);
    items.truncate(100);
    Ok(Json(HomeAgentPage { items, next_cursor }))
}
#[utoipa::path(get,path="/spaces/{organization_id}/home",params(("organization_id"=Uuid,Path)),responses((status=200,body=HomeShowcase),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody)))]
async fn organization_home(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<Json<HomeShowcase>> {
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read read only")
        .execute(&mut *tx)
        .await?;
    let facts = authorization::load_facts(&mut *tx, &user.uid, id).await?;
    if facts.space.kind != SpaceKind::Organization || !facts.in_organization {
        return Err(AppError::NotFound);
    }
    facts.require_active()?;
    let (layout, _, _) = settings(&mut *tx, id).await?;
    let saved = entries(&mut *tx, id).await?;
    let ids: Vec<_> = saved.iter().map(|e| e.agent_instance_id).collect();
    let visible = available(&mut *tx, &s, &user.uid, id, Some(&ids), None, false).await?;
    let mut featured = vec![];
    let mut ask_agent = None;
    if matches!(layout, HomeLayout::Advanced) {
        for e in saved {
            if let Some(agent) = visible
                .iter()
                .find(|a| a.agent_instance_id == e.agent_instance_id)
                .cloned()
            {
                if e.position == -1 {
                    ask_agent = Some(agent)
                } else {
                    featured.push(FeaturedHomeAgent {
                        agent,
                        badge: e.badge,
                        highlights: e.highlights,
                    })
                }
            }
        }
    }
    let recent_agents = available(&mut *tx, &s, &user.uid, id, None, None, true).await?;
    tx.commit().await?;
    Ok(Json(HomeShowcase {
        recent_agents,
        layout,
        featured,
        ask_agent,
    }))
}
#[utoipa::path(put,path="/spaces/{organization_id}/home-settings",params(("organization_id"=Uuid,Path)),request_body=SetOrganizationHomeRequest,responses((status=204),(status=400,body=crate::error::ErrorBody),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody)))]
async fn set_organization_home(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    ApiJson(mut body): ApiJson<SetOrganizationHomeRequest>,
) -> AppResult<StatusCode> {
    let mut tx = s.pool.begin().await?;
    crate::spaces::lock_organization_id(&mut tx, id).await?;
    owner(&mut *tx, &user.uid, id).await?;
    let mut ids = HashSet::new();
    if body.featured.len() > 10 {
        return Err(AppError::BadRequest("at most 10 featured agents".into()));
    }
    for e in &mut body.featured {
        if !ids.insert(e.agent_instance_id) {
            return Err(AppError::BadRequest("duplicate featured agent".into()));
        }
        e.badge = e.badge.take().map(|s| s.trim().to_owned());
        for text in &mut e.highlights {
            *text = text.trim().to_owned()
        }
        if e.badge
            .as_ref()
            .is_some_and(|s| s.is_empty() || s.chars().count() > 20)
            || e.highlights.len() > 4
            || e.highlights
                .iter()
                .any(|s| s.is_empty() || s.chars().count() > 80)
        {
            return Err(AppError::BadRequest("invalid badge or highlights".into()));
        }
    }
    ids.extend(body.ask_agent_instance_id);
    let ids: Vec<_> = ids.into_iter().collect();
    let visible = available(&mut *tx, &s, &user.uid, id, Some(&ids), None, false).await?;
    let previous = entries(&mut *tx, id).await?;
    // Previously saved unavailable entries can be retained/reordered without exposing their content.
    if ids.iter().any(|id| {
        !visible.iter().any(|a| a.agent_instance_id == *id)
            && !previous.iter().any(|e| e.agent_instance_id == *id)
    }) {
        return Err(AppError::NotFound);
    }
    sqlx::query("insert into organization_home_settings(organization_id,layout,updated_by) values($1,$2,$3) on conflict(organization_id) do update set layout=excluded.layout,updated_by=excluded.updated_by,updated_at=now()")
        .bind(id).bind(body.layout.as_str()).bind(&user.uid).execute(&mut *tx).await?;
    sqlx::query("delete from organization_home_agent where organization_id=$1")
        .bind(id)
        .execute(&mut *tx)
        .await?;
    if let Some(ask) = body.ask_agent_instance_id {
        sqlx::query("insert into organization_home_agent(organization_id,position,agent_instance_id) values($1,-1,$2)").bind(id).bind(ask).execute(&mut *tx).await?;
    }
    for (position, e) in body.featured.iter().enumerate() {
        sqlx::query("insert into organization_home_agent(organization_id,position,agent_instance_id,badge,highlights) values($1,$2,$3,$4,$5)")
        .bind(id).bind(position as i16).bind(e.agent_instance_id).bind(&e.badge).bind(&e.highlights).execute(&mut *tx).await?;
    }
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}
