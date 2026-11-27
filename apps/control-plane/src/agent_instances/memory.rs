// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Shared memory of one agent instance: short notes visible to every member using it.
//! Editors manage notes from the agent settings; a person's own conversation with the
//! instance may remember and forget notes through its delegated workload. This is a
//! deliberate exception to delegated calls being read-only elsewhere: the person
//! only needs Read on the space (checked at turn admission), and the conversation
//! binding is checked on every call. Editing a note forgets it and remembers its
//! replacement in one transaction; the replacement keeps the original creation date.

use axum::{
    Json,
    extract::{FromRef, State},
    http::StatusCode,
};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::{Postgres, Transaction};
use utoipa::ToSchema;
use utoipa_axum::{router::OpenApiRouter, routes};
use uuid::Uuid;

use crate::{
    api::AppState,
    auth::CurrentUser,
    authorization::{self, Delegation, RuntimeCaller},
    domain::Space,
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath, ApiQuery},
    onboarding,
    roles::SpacePermission,
    spaces,
};

use super::require_instance_space;

const MAX_ACTIVE_NOTES: i64 = 50;
const MAX_NOTE_CHARS: usize = 500;
/// Most recently forgotten notes returned as history; older history stays stored.
const HISTORY_SIZE: i64 = 200;

pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(agent_memory, remember_agent_memory_note))
        .routes(routes!(edit_agent_memory_note, forget_agent_memory_note))
}

#[derive(Deserialize)]
struct MemoryQuery {
    #[serde(flatten)]
    delegation: Delegation,
    /// The delegated conversation; refused for a person's own call.
    session_id: Option<Uuid>,
    /// Flattened query values stay strings; parsed explicitly.
    include_forgotten: Option<String>,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct RememberAgentMemoryNoteRequest {
    /// Trimmed before storage.
    #[schema(min_length = 1, max_length = 500)]
    pub content: String,
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct AgentMemoryNote {
    pub note_id: Uuid,
    pub content: String,
    pub created_by: String,
    /// Directory name, for a person's own call only.
    #[sqlx(skip)]
    #[schema(required = true)]
    pub created_by_name: Option<String>,
    /// Null when the note was added from the agent settings.
    #[schema(required = true)]
    pub created_session_id: Option<Uuid>,
    pub created_at: DateTime<Utc>,
    /// The note this one replaced; null for a note created from scratch.
    #[schema(required = true)]
    pub revises_note_id: Option<Uuid>,
    /// Creation date of the first version: the active list keeps edited notes in place.
    pub origin_created_at: DateTime<Utc>,
    #[schema(required = true)]
    pub forgotten_by: Option<String>,
    #[sqlx(skip)]
    #[schema(required = true)]
    pub forgotten_by_name: Option<String>,
    /// Null while the note is active.
    #[schema(required = true)]
    pub forgotten_at: Option<DateTime<Utc>>,
}

#[derive(Serialize, ToSchema)]
pub struct AgentMemory {
    /// Active notes oldest first by original creation, then (on request) the most recently forgotten first.
    pub notes: Vec<AgentMemoryNote>,
}

struct Access {
    tx: Transaction<'static, Postgres>,
    person: String,
    /// The delegated conversation, once bound to this person, space and instance.
    session: Option<Uuid>,
    editor: bool,
}

/// One short transaction: no network call or human wait occurs inside it.
async fn open(
    state: &AppState,
    caller: &CurrentUser,
    query: &MemoryQuery,
    space_id: Uuid,
    agent_instance_id: Uuid,
    mutation: bool,
) -> AppResult<Access> {
    let person = query.delegation.subject(state, caller)?.to_owned();
    let delegated = query.delegation.agent.is_some();
    if delegated {
        let bound = query
            .delegation
            .agent
            .as_deref()
            .and_then(|id| Uuid::parse_str(id).ok());
        if bound != Some(agent_instance_id) {
            return Err(AppError::NotFound);
        }
        if query.session_id.is_none() {
            return Err(AppError::Unprocessable(
                "The bound conversation is required.".into(),
            ));
        }
    } else {
        if query.session_id.is_some() {
            return Err(AppError::Unprocessable(
                "session_id is reserved to delegated calls.".into(),
            ));
        }
        let admission = onboarding::AdmissionState::from_ref(state);
        onboarding::require_admitted(&admission.pool, &admission.auth, &person).await?;
        if admission.auth.enabled() {
            onboarding::require_accepted(&admission.pool, admission.version.as_deref(), &person)
                .await?;
        }
        crate::users::snapshot(&admission, caller).await;
    }
    let mut tx = spaces::storage_transaction(&state.pool, space_id, true).await?;
    let (space, editor) = if delegated {
        // Admission already checked the person's direct space rights for a delegated
        // turn. Only the live conversation binding is checked again below.
        (
            Space::from(crate::db::space(&mut *tx, space_id).await?),
            false,
        )
    } else {
        let facts = authorization::load_facts(&mut *tx, &person, space_id).await?;
        authorization::decide(&facts, SpacePermission::Read)?;
        let editor = authorization::decide(&facts, SpacePermission::Write).is_ok();
        (Space::from(facts.space), editor)
    };
    require_instance_space(space.kind)?;
    crate::lifecycle::store::require_active(&mut *tx, space.id).await?;
    crate::lifecycle::store::require_active(&mut *tx, space.organization).await?;
    // Holding the instance row serializes the active-note cap without blocking
    // the foreign-key checks of concurrent inserts. Like instance deletion, notes
    // stay manageable after the template is revoked: they disclose nothing of it.
    sqlx::query_scalar::<_, i32>(if mutation {
        "select 1 from agent_instance where agent_instance_id=$1 and space_id=$2 for no key update"
    } else {
        "select 1 from agent_instance where agent_instance_id=$1 and space_id=$2"
    })
    .bind(agent_instance_id)
    .bind(space_id)
    .fetch_optional(&mut *tx)
    .await?
    .ok_or(AppError::NotFound)?;
    let session = if delegated {
        // The conversation belongs to the person, in this space, with this instance.
        let session = query.session_id;
        let owned: bool = sqlx::query_scalar(
            "select exists(select 1 from session_metadata where session_id=$1 and space_id=$2
             and user_id=$3 and agent_instance_id=$4 and deletion_id is null)",
        )
        .bind(session)
        .bind(space_id)
        .bind(&person)
        .bind(agent_instance_id)
        .fetch_one(&mut *tx)
        .await?;
        if !owned {
            return Err(AppError::NotFound);
        }
        session
    } else {
        None
    };
    Ok(Access {
        tx,
        person,
        session,
        editor,
    })
}

async fn name_notes(s: &AppState, notes: &mut [AgentMemoryNote]) {
    let subjects = notes
        .iter()
        .flat_map(|note| std::iter::once(note.created_by.clone()).chain(note.forgotten_by.clone()))
        .collect();
    let names = async {
        crate::api::organization_directory(s)?
            .display_names(subjects)
            .await
    };
    let names = names.await.unwrap_or_else(|_| {
        tracing::warn!("Agent memory author names unavailable");
        Default::default()
    });
    for note in notes {
        note.created_by_name = names.get(&note.created_by).cloned();
        note.forgotten_by_name = note
            .forgotten_by
            .as_ref()
            .and_then(|id| names.get(id))
            .cloned();
    }
}

/// The stored form of a note's content: trimmed, 1..=500 characters.
fn note_content(raw: &str) -> AppResult<&str> {
    let content = raw.trim();
    if !(1..=MAX_NOTE_CHARS).contains(&content.chars().count()) || content.contains('\0') {
        return Err(AppError::Unprocessable(format!(
            "content: expected 1..{MAX_NOTE_CHARS} characters after trimming"
        )));
    }
    Ok(content)
}

/// People change the memory from the settings; conversations through the delegated turn.
async fn open_writer(
    state: &AppState,
    caller: &CurrentUser,
    query: &MemoryQuery,
    space_id: Uuid,
    agent_instance_id: Uuid,
) -> AppResult<Access> {
    let access = open(state, caller, query, space_id, agent_instance_id, true).await?;
    if access.session.is_none() && !access.editor {
        return Err(AppError::Forbidden);
    }
    Ok(access)
}

macro_rules! note_columns {
    () => {
        "note_id,content,created_by,created_session_id,created_at,revises_note_id,origin_created_at,forgotten_by,forgotten_at"
    };
}

#[utoipa::path(get, path = "/spaces/{space_id}/agent-instances/{agent_instance_id}/memory",
    operation_id = "agent_memory",
    params(("space_id" = Uuid, Path), ("agent_instance_id" = Uuid, Path),
        ("include_forgotten" = Option<bool>, Query, description = "Also return recent history"),
        ("person" = Option<String>, Query), ("run" = Option<String>, Query),
        ("agent" = Option<String>, Query), ("session_id" = Option<Uuid>, Query)),
    responses((status = 200, body = AgentMemory), (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody), (status = 404, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody)))]
async fn agent_memory(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath((space_id, agent_instance_id)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(q): ApiQuery<MemoryQuery>,
) -> AppResult<Json<AgentMemory>> {
    let history = match q.include_forgotten.as_deref() {
        None | Some("false") => false,
        Some("true") => true,
        Some(_) => {
            return Err(AppError::Unprocessable(
                "include_forgotten: expected true or false".into(),
            ));
        }
    };
    let mut access = open(&s, &user, &q, space_id, agent_instance_id, false).await?;
    let mut notes: Vec<AgentMemoryNote> = sqlx::query_as(concat!(
        "select ",
        note_columns!(),
        " from agent_memory_note where agent_instance_id=$1
         and forgotten_at is null order by origin_created_at, created_at, note_id"
    ))
    .bind(agent_instance_id)
    .fetch_all(&mut *access.tx)
    .await?;
    if history {
        notes.extend(
            sqlx::query_as::<_, AgentMemoryNote>(concat!(
                "select ",
                note_columns!(),
                " from agent_memory_note where agent_instance_id=$1
                 and forgotten_at is not null order by forgotten_at desc, note_id limit $2"
            ))
            .bind(agent_instance_id)
            .bind(HISTORY_SIZE)
            .fetch_all(&mut *access.tx)
            .await?,
        );
    }
    access.tx.commit().await?;
    // The directory can be remote: call it only after releasing the transaction.
    if access.session.is_none() {
        name_notes(&s, &mut notes).await;
    }
    Ok(Json(AgentMemory { notes }))
}

#[utoipa::path(post, path = "/spaces/{space_id}/agent-instances/{agent_instance_id}/memory",
    operation_id = "remember_agent_memory_note",
    params(("space_id" = Uuid, Path), ("agent_instance_id" = Uuid, Path),
        ("person" = Option<String>, Query), ("run" = Option<String>, Query),
        ("agent" = Option<String>, Query), ("session_id" = Option<Uuid>, Query)),
    request_body = RememberAgentMemoryNoteRequest,
    responses((status = 201, body = AgentMemoryNote),
        (status = 200, body = AgentMemoryNote, description = "The same active note already exists"),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody), (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody, description = "memory_full: 50 active notes"),
        (status = 422, body = crate::error::ErrorBody)))]
async fn remember_agent_memory_note(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath((space_id, agent_instance_id)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(q): ApiQuery<MemoryQuery>,
    ApiJson(body): ApiJson<RememberAgentMemoryNoteRequest>,
) -> AppResult<(StatusCode, Json<AgentMemoryNote>)> {
    let content = note_content(&body.content)?;
    let mut access = open_writer(&s, &user, &q, space_id, agent_instance_id).await?;
    // Retries and re-remembering the same fact return the existing active note.
    let existing: Option<AgentMemoryNote> = sqlx::query_as(concat!(
        "select ",
        note_columns!(),
        " from agent_memory_note where agent_instance_id=$1 and forgotten_at is null
         and content=$2 order by created_at limit 1"
    ))
    .bind(agent_instance_id)
    .bind(content)
    .fetch_optional(&mut *access.tx)
    .await?;
    if let Some(mut note) = existing {
        access.tx.commit().await?;
        if access.session.is_none() {
            name_notes(&s, std::slice::from_mut(&mut note)).await;
        }
        return Ok((StatusCode::OK, Json(note)));
    }
    let active: i64 = sqlx::query_scalar(
        "select count(*) from agent_memory_note where agent_instance_id=$1 and forgotten_at is null",
    )
    .bind(agent_instance_id)
    .fetch_one(&mut *access.tx)
    .await?;
    if active >= MAX_ACTIVE_NOTES {
        return Err(AppError::problem(
            StatusCode::CONFLICT,
            "memory_full",
            "The agent memory already holds 50 notes; forget one first.",
        ));
    }
    let mut note: AgentMemoryNote = sqlx::query_as(concat!(
        "with clock as (select clock_timestamp() as ts)
         insert into agent_memory_note(note_id,space_id,agent_instance_id,content,created_by,
             created_session_id,created_at,origin_created_at)
         select $1,$2,$3,$4,$5,$6,ts,ts from clock returning ",
        note_columns!()
    ))
    .bind(Uuid::new_v4())
    .bind(space_id)
    .bind(agent_instance_id)
    .bind(content)
    .bind(&access.person)
    .bind(access.session)
    .fetch_one(&mut *access.tx)
    .await?;
    access.tx.commit().await?;
    tracing::info!(target: "fred.security.audit", audit_event = "agent_memory.note_added",
        actor_uid = %access.person, space_id = %space_id, agent_instance_id = %agent_instance_id,
        note_id = %note.note_id, delegated = access.session.is_some(),
        session_id = ?access.session, outcome = "succeeded", "Agent memory note added");
    if access.session.is_none() {
        name_notes(&s, std::slice::from_mut(&mut note)).await;
    }
    Ok((StatusCode::CREATED, Json(note)))
}

#[utoipa::path(patch, path = "/spaces/{space_id}/agent-instances/{agent_instance_id}/memory/{note_id}",
    operation_id = "edit_agent_memory_note",
    params(("space_id" = Uuid, Path), ("agent_instance_id" = Uuid, Path), ("note_id" = Uuid, Path),
        ("person" = Option<String>, Query), ("run" = Option<String>, Query),
        ("agent" = Option<String>, Query), ("session_id" = Option<Uuid>, Query)),
    request_body = RememberAgentMemoryNoteRequest,
    responses((status = 200, body = AgentMemoryNote,
            description = "The replacing note, or the same note when its content is unchanged"),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody), (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody,
            description = "memory_note_forgotten: the note was already forgotten or replaced"),
        (status = 422, body = crate::error::ErrorBody)))]
async fn edit_agent_memory_note(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath((space_id, agent_instance_id, note_id)): ApiPath<(Uuid, Uuid, Uuid)>,
    ApiQuery(q): ApiQuery<MemoryQuery>,
    ApiJson(body): ApiJson<RememberAgentMemoryNoteRequest>,
) -> AppResult<Json<AgentMemoryNote>> {
    let content = note_content(&body.content)?;
    let mut access = open_writer(&s, &user, &q, space_id, agent_instance_id).await?;
    let mut note: AgentMemoryNote = sqlx::query_as(concat!(
        "select ",
        note_columns!(),
        " from agent_memory_note where note_id=$1 and agent_instance_id=$2 for update"
    ))
    .bind(note_id)
    .bind(agent_instance_id)
    .fetch_optional(&mut *access.tx)
    .await?
    .ok_or(AppError::NotFound)?;
    // Someone else forgot or edited it meanwhile: the edit would resurrect a stale note.
    if note.forgotten_at.is_some() {
        return Err(AppError::problem(
            StatusCode::CONFLICT,
            "memory_note_forgotten",
            "This note was already forgotten or replaced.",
        ));
    }
    if note.content != content {
        sqlx::query(
            "update agent_memory_note set forgotten_by=$2,forgotten_session_id=$3,forgotten_at=clock_timestamp()
             where note_id=$1",
        )
        .bind(note_id)
        .bind(&access.person)
        .bind(access.session)
        .execute(&mut *access.tx)
        .await?;
        // The count of active notes is unchanged, so the cap needs no check.
        note = sqlx::query_as(concat!(
            "insert into agent_memory_note(note_id,space_id,agent_instance_id,content,created_by,
                 created_session_id,revises_note_id,origin_created_at)
             values($1,$2,$3,$4,$5,$6,$7,$8) returning ",
            note_columns!()
        ))
        .bind(Uuid::new_v4())
        .bind(space_id)
        .bind(agent_instance_id)
        .bind(content)
        .bind(&access.person)
        .bind(access.session)
        .bind(note_id)
        .bind(note.origin_created_at)
        .fetch_one(&mut *access.tx)
        .await?;
        access.tx.commit().await?;
        tracing::info!(target: "fred.security.audit", audit_event = "agent_memory.note_edited",
            actor_uid = %access.person, space_id = %space_id, agent_instance_id = %agent_instance_id,
            note_id = %note.note_id, revises_note_id = %note_id, delegated = access.session.is_some(),
            session_id = ?access.session, outcome = "succeeded", "Agent memory note edited");
    } else {
        access.tx.commit().await?;
    }
    if access.session.is_none() {
        name_notes(&s, std::slice::from_mut(&mut note)).await;
    }
    Ok(Json(note))
}

#[utoipa::path(delete, path = "/spaces/{space_id}/agent-instances/{agent_instance_id}/memory/{note_id}",
    operation_id = "forget_agent_memory_note",
    params(("space_id" = Uuid, Path), ("agent_instance_id" = Uuid, Path), ("note_id" = Uuid, Path),
        ("person" = Option<String>, Query), ("run" = Option<String>, Query),
        ("agent" = Option<String>, Query), ("session_id" = Option<Uuid>, Query)),
    responses((status = 204, description = "Forgotten, or already forgotten"),
        (status = 401, body = crate::error::ErrorBody), (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody), (status = 422, body = crate::error::ErrorBody)))]
async fn forget_agent_memory_note(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath((space_id, agent_instance_id, note_id)): ApiPath<(Uuid, Uuid, Uuid)>,
    ApiQuery(q): ApiQuery<MemoryQuery>,
) -> AppResult<StatusCode> {
    let mut access = open(&s, &user, &q, space_id, agent_instance_id, true).await?;
    let (created_by, forgotten): (String, bool) = sqlx::query_as(
        "select created_by,forgotten_at is not null from agent_memory_note
         where note_id=$1 and agent_instance_id=$2 for update",
    )
    .bind(note_id)
    .bind(agent_instance_id)
    .fetch_optional(&mut *access.tx)
    .await?
    .ok_or(AppError::NotFound)?;
    // A member may undo their own note from the chat without editing the agent.
    if access.session.is_none() && !access.editor && created_by != access.person {
        return Err(AppError::Forbidden);
    }
    if forgotten {
        access.tx.commit().await?;
        return Ok(StatusCode::NO_CONTENT);
    }
    sqlx::query(
        "update agent_memory_note set forgotten_by=$2,forgotten_session_id=$3,forgotten_at=clock_timestamp()
         where note_id=$1",
    )
    .bind(note_id)
    .bind(&access.person)
    .bind(access.session)
    .execute(&mut *access.tx)
    .await?;
    access.tx.commit().await?;
    tracing::info!(target: "fred.security.audit", audit_event = "agent_memory.note_forgotten",
        actor_uid = %access.person, space_id = %space_id, agent_instance_id = %agent_instance_id,
        note_id = %note_id, delegated = access.session.is_some(),
        session_id = ?access.session, outcome = "succeeded", "Agent memory note forgotten");
    Ok(StatusCode::NO_CONTENT)
}
