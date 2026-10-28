// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Private product metadata. Provenance is immutable; runtime storage is not read
//! or synchronized here, and deleting an instance never deletes this index.
//! A deleted session is retired at once and absent from every read below.

use axum::{
    Json,
    extract::State,
    http::{StatusCode, header},
    response::IntoResponse,
};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

use crate::{
    agent_instances::{self, AgentInstance},
    api::AppState,
    domain::Permission,
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath},
    onboarding::{self, AdmittedUser},
    spaces,
};

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CreateSessionRequest {
    /// Frontend-generated identifier, retained verbatim.
    pub session_id: Uuid,
    pub agent_instance_id: Uuid,
    #[schema(max_length = 500)]
    pub title: Option<String>,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UpdateSessionRequest {
    /// Omitted/null keeps the current title; an empty string explicitly clears it.
    #[schema(max_length = 500)]
    pub title: Option<String>,
    /// Last observed activity. Monotonic, capped at server time; omission keeps activity.
    pub updated_at: Option<DateTime<Utc>>,
}

#[derive(sqlx::FromRow)]
pub(crate) struct SessionRecord {
    session_id: Uuid,
    space_id: Uuid,
    agent_instance_id: Uuid,
    template_id: Uuid,
    runtime_id: String,
    agent_display_name: String,
    title: Option<String>,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>,
    agent_deleted: bool,
    agent_disabled: bool,
}

#[derive(Serialize, ToSchema)]
pub struct SessionDetails {
    pub session_id: Uuid,
    pub space_id: Uuid,
    pub agent_instance_id: Uuid,
    pub template_id: Uuid,
    pub runtime_id: String,
    /// Current name, or the registration snapshot after instance removal.
    pub agent_display_name: String,
    #[schema(required = true)]
    pub title: Option<String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub agent_deleted: bool,
    pub agent_disabled: bool,
    /// Public history destination, independent of instance/template execution state.
    /// Null if this runtime has no enabled, platform-approved public route.
    #[schema(required = true)]
    pub messages_url: Option<String>,
}

const SELECT: &str = "select s.session_id, s.user_id, s.space_id, s.agent_instance_id,
    s.template_id, s.runtime_id, coalesce(a.display_name, s.agent_display_name) as agent_display_name,
    s.title, s.created_at, s.updated_at, a.agent_instance_id is null as agent_deleted,
    coalesce(not a.enabled, false) as agent_disabled
    from session_metadata s left join agent_instance a
    on a.agent_instance_id = s.agent_instance_id and a.space_id = s.space_id
    where s.space_id = $1 and s.user_id = $2 and ($3::uuid is null or s.session_id = $3)
      and s.deletion_id is null
    order by s.updated_at desc, s.session_id";

fn validate_title(title: Option<&str>) -> AppResult<()> {
    if title.is_some_and(|title| title.chars().count() > 500) {
        return Err(AppError::Unprocessable(
            "Session title must contain at most 500 characters.".into(),
        ));
    }
    Ok(())
}

async fn owned<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    space_id: Uuid,
    user_id: &str,
    session_id: Uuid,
) -> AppResult<SessionRecord> {
    sqlx::query_as(SELECT)
        .bind(space_id)
        .bind(user_id)
        .bind(session_id)
        .fetch_optional(ex)
        .await?
        .ok_or(AppError::NotFound)
}

/// Called inside the existing resolver request, before runtime can pin or load
/// its local checkpoint association. No per-LLM-call or cross-store lookup.
pub(crate) async fn require_association<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    subject: &str,
    session_id: &str,
    instance: &AgentInstance,
) -> AppResult<()> {
    let session_id = Uuid::parse_str(session_id)
        .map_err(|_| AppError::Unprocessable("Invalid session identifier.".into()))?;
    let record = owned(ex, instance.space_id, subject, session_id).await?;
    if record.agent_instance_id != instance.agent_instance_id
        || record.template_id != instance.template_id
        || record.runtime_id != instance.source_runtime_id
    {
        return Err(association_conflict());
    }
    Ok(())
}

fn association_conflict() -> AppError {
    AppError::problem(
        StatusCode::CONFLICT,
        "session_association_mismatch",
        "The session is already associated with another agent instance or runtime.",
    )
}

fn details(state: &AppState, record: SessionRecord) -> SessionDetails {
    let messages_url =
        crate::agent_instances::preparation::public_base(&state.agent_catalog, &record.runtime_id)
            .map(|base| format!("{base}/agents/sessions/{}/messages", record.session_id));
    SessionDetails {
        session_id: record.session_id,
        space_id: record.space_id,
        agent_instance_id: record.agent_instance_id,
        template_id: record.template_id,
        runtime_id: record.runtime_id,
        agent_display_name: record.agent_display_name,
        title: record.title,
        created_at: record.created_at,
        updated_at: record.updated_at,
        agent_deleted: record.agent_deleted,
        agent_disabled: record.agent_disabled,
        messages_url,
    }
}

pub fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new()
        .routes(utoipa_axum::routes!(create_session))
        .routes(utoipa_axum::routes!(list_sessions))
        .routes(utoipa_axum::routes!(get_session))
        .routes(utoipa_axum::routes!(update_session))
        .routes(utoipa_axum::routes!(delete_session))
}

#[utoipa::path(post, path = "/spaces/{space_id}/sessions",
    params(("space_id" = Uuid, Path)), request_body = CreateSessionRequest,
    responses((status = 201, body = SessionDetails), (status = 200, body = SessionDetails),
        (status = 400, body = crate::error::ErrorBody), (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody), (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody), (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody), (status = 503, body = crate::error::ErrorBody))) ]
async fn create_session(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space_id): ApiPath<Uuid>,
    ApiJson(body): ApiJson<CreateSessionRequest>,
) -> AppResult<impl IntoResponse> {
    validate_title(body.title.as_deref())?;
    let space = spaces::authorize(&s.pool, &s.fga, &user.uid, space_id, Permission::Read).await?;
    agent_instances::http::require_instance_space(space.kind)?;
    let (mut tx, mut guard) = spaces::lock_for(&s.pool, &s.fga, &space).await?;
    let space =
        spaces::authorize_locked(&mut tx, &s.fga, &user.uid, space_id, Permission::Read).await?;
    onboarding::require_accepted(&mut *tx, s.onboarding.gcu_version.as_deref(), &user.uid).await?;
    let existing: bool =
        sqlx::query_scalar("select exists(select 1 from session_metadata where session_id = $1)")
            .bind(body.session_id)
            .fetch_one(&mut *tx)
            .await?;
    let mut status = StatusCode::OK;
    if !existing {
        let instance = agent_instances::get_for_space(&mut *tx, space_id, body.agent_instance_id)
            .await?
            .ok_or(AppError::NotFound)?;
        if !s.fga.can_use_agent(instance.template_id, &space).await? {
            return Err(AppError::NotFound);
        }
        agent_instances::require_executable(&s, &space, &instance)?;
        s.fga.fence(&mut guard).await?;
        let inserted = sqlx::query("insert into session_metadata
            (session_id, user_id, space_id, agent_instance_id, template_id, runtime_id, agent_display_name, title)
            values ($1,$2,$3,$4,$5,$6,$7,$8) on conflict (session_id) do nothing")
            .bind(body.session_id).bind(&user.uid).bind(space_id).bind(instance.agent_instance_id)
            .bind(instance.template_id).bind(&instance.source_runtime_id).bind(&instance.display_name)
            .bind(&body.title).execute(&mut *tx).await?;
        if inserted.rows_affected() == 1 {
            status = StatusCode::CREATED;
        }
    }
    // A retry returns the original row, including its title/activity. It cannot
    // seize another owner's ID, move a session or revive a deleted one.
    let record = owned(&mut *tx, space_id, &user.uid, body.session_id).await?;
    if record.agent_instance_id != body.agent_instance_id {
        return Err(association_conflict());
    }
    tx.commit().await?;
    Ok((
        status,
        [(header::CACHE_CONTROL, "no-store")],
        Json(details(&s, record)),
    ))
}

#[utoipa::path(get, path = "/spaces/{space_id}/sessions", params(("space_id" = Uuid, Path)),
    responses((status = 200, body = [SessionDetails]),
        (status = 401, body = crate::error::ErrorBody), (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody), (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody), (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody))) ]
async fn list_sessions(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space_id): ApiPath<Uuid>,
) -> AppResult<impl IntoResponse> {
    spaces::authorize(&s.pool, &s.fga, &user.uid, space_id, Permission::Read).await?;
    let records: Vec<SessionRecord> = sqlx::query_as(SELECT)
        .bind(space_id)
        .bind(&user.uid)
        .bind(None::<Uuid>)
        .fetch_all(&s.pool)
        .await?;
    let records: Vec<_> = records
        .into_iter()
        .map(|record| details(&s, record))
        .collect();
    Ok(([(header::CACHE_CONTROL, "no-store")], Json(records)))
}

#[utoipa::path(get, path = "/spaces/{space_id}/sessions/{session_id}",
    params(("space_id" = Uuid, Path), ("session_id" = Uuid, Path)),
    responses((status = 200, body = SessionDetails),
        (status = 401, body = crate::error::ErrorBody), (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody), (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody), (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody))) ]
async fn get_session(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space_id, session_id)): ApiPath<(Uuid, Uuid)>,
) -> AppResult<impl IntoResponse> {
    spaces::authorize(&s.pool, &s.fga, &user.uid, space_id, Permission::Read).await?;
    let record = owned(&s.pool, space_id, &user.uid, session_id).await?;
    Ok((
        [(header::CACHE_CONTROL, "no-store")],
        Json(details(&s, record)),
    ))
}

#[utoipa::path(patch, path = "/spaces/{space_id}/sessions/{session_id}",
    params(("space_id" = Uuid, Path), ("session_id" = Uuid, Path)), request_body = UpdateSessionRequest,
    responses((status = 200, body = SessionDetails), (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody), (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody), (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody), (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody))) ]
async fn update_session(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space_id, session_id)): ApiPath<(Uuid, Uuid)>,
    ApiJson(body): ApiJson<UpdateSessionRequest>,
) -> AppResult<impl IntoResponse> {
    validate_title(body.title.as_deref())?;
    let space = spaces::authorize(&s.pool, &s.fga, &user.uid, space_id, Permission::Read).await?;
    let (mut tx, mut guard) = spaces::lock_for(&s.pool, &s.fga, &space).await?;
    spaces::authorize_locked(&mut tx, &s.fga, &user.uid, space_id, Permission::Read).await?;
    onboarding::require_accepted(&mut *tx, s.onboarding.gcu_version.as_deref(), &user.uid).await?;
    s.fga.fence(&mut guard).await?;
    sqlx::query(
        "update session_metadata set title = coalesce($4, title),
        updated_at = greatest(updated_at, least(coalesce($5, updated_at), clock_timestamp()))
        where space_id = $1 and user_id = $2 and session_id = $3",
    )
    .bind(space_id)
    .bind(&user.uid)
    .bind(session_id)
    .bind(&body.title)
    .bind(body.updated_at)
    .execute(&mut *tx)
    .await?;
    let record = owned(&mut *tx, space_id, &user.uid, session_id).await?;
    tx.commit().await?;
    Ok((
        [(header::CACHE_CONTROL, "no-store")],
        Json(details(&s, record)),
    ))
}

#[utoipa::path(delete, path = "/spaces/{space_id}/sessions/{session_id}",
    params(("space_id" = Uuid, Path), ("session_id" = Uuid, Path)),
    responses((status = 202, body = crate::lifecycle::Receipt), (status = 200, body = crate::lifecycle::Receipt),
        (status = 401, body = crate::error::ErrorBody), (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody), (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody), (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody))) ]
async fn delete_session(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space_id, session_id)): ApiPath<(Uuid, Uuid)>,
) -> AppResult<impl IntoResponse> {
    let receipt = s
        .lifecycle
        .accept_session(&s.pool, &s.fga, &user.uid, space_id, session_id)
        .await?;
    Ok((
        if receipt.status == crate::lifecycle::Status::Completed {
            StatusCode::OK
        } else {
            StatusCode::ACCEPTED
        },
        Json(receipt),
    ))
}
