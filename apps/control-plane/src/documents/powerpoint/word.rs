// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
//! Word library selection reuses original receipts and per-file preparation.
use super::*;
use crate::{
    api::AppState,
    capability_preparation,
    extract::{ApiJson, ApiPath, ApiQuery, idempotency_key},
    onboarding::AdmittedUser,
};
use axum::{
    Json,
    extract::{DefaultBodyLimit, State},
    http::{HeaderMap, HeaderValue},
};
use serde_json::{Value, json};
use utoipa_axum::{
    router::{OpenApiRouter, UtoipaMethodRouterExt},
    routes,
};

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct LibraryEntry {
    pub file_id: Uuid,
    pub label: String,
}
#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct LibraryChange {
    pub files: Vec<LibraryEntry>,
    pub expected_file_ids: Vec<Uuid>,
}
#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct LibraryFile {
    #[sqlx(flatten)]
    pub file: PowerPointFile,
    pub label: String,
    pub preparation_state: String,
    pub preparation_error: Option<String>,
}
#[derive(Serialize, ToSchema)]
pub struct Library {
    pub source: PowerPointSource,
    pub files: Vec<LibraryFile>,
    pub own_file_ids: Vec<Uuid>,
    pub activation_ready: bool,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Target {
    agent_instance_id: Option<Uuid>,
    runtime_id: Option<String>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct UploadTarget {
    agent_instance_id: Option<Uuid>,
    runtime_id: Option<String>,
    template_id: Option<Uuid>,
    expected_file_id: Option<Uuid>,
    slot: i16,
}

fn selected(record: &crate::agent_instances::AgentInstance) -> bool {
    record
        .tuning
        .0
        .get("selected_capability_ids")
        .and_then(Value::as_array)
        .is_some_and(|ids| ids.iter().any(|id| id == "word_template"))
}
fn validate(change: &LibraryChange) -> AppResult<()> {
    let ids: std::collections::BTreeSet<_> = change.files.iter().map(|f| f.file_id).collect();
    let labels: std::collections::BTreeSet<_> = change
        .files
        .iter()
        .map(|f| f.label.trim().to_lowercase())
        .collect();
    if change.files.len() > 8
        || change.expected_file_ids.len() > 16
        || ids.len() != change.files.len()
        || labels.len() != change.files.len()
        || change
            .files
            .iter()
            .any(|f| f.label.trim().is_empty() || f.label.len() > 255)
    {
        return Err(AppError::Unprocessable(
            "A Word library requires up to eight files with distinct names".into(),
        ));
    }
    Ok(())
}
async fn own<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    space: Uuid,
    agent: Option<Uuid>,
    runtime: &str,
) -> AppResult<Vec<Uuid>> {
    Ok(sqlx::query_scalar("select id from powerpoint_file where space_id=$1 and agent_instance_id is not distinct from $2 and runtime_id=$3 and capability_id='word_template' and status='stored' order by slot,effective")
        .bind(space).bind(agent).bind(runtime).fetch_all(ex).await?)
}

/// Bounded pod validation precedes the save transaction. Every receipt is checked again on attach.
pub(crate) async fn preflight(
    s: &AppState,
    user: &CurrentUser,
    space: Uuid,
    agent: Option<Uuid>,
    runtime: &str,
    change: &LibraryChange,
    authorization: Option<&HeaderValue>,
) -> AppResult<Option<Uuid>> {
    validate(change)?;
    let mut draft = agent;
    for entry in &change.files {
        let row: FileRow = sqlx::query_as("select * from powerpoint_file where id=$1")
            .bind(entry.file_id)
            .fetch_optional(&s.pool)
            .await?
            .ok_or(AppError::NotFound)?;
        if row.file.space_id != space
            || row.file.runtime_id.as_deref() != Some(runtime)
            || row.file.capability_id != "word_template"
            || agent.is_some_and(|a| Some(a) != row.file.agent_instance_id)
        {
            return Err(AppError::NotFound);
        }
        if draft.is_some() && draft != row.file.agent_instance_id {
            return Err(AppError::Unprocessable(
                "Word receipts belong to different instances".into(),
            ));
        }
        draft = row.file.agent_instance_id;
        if row.file.status == PowerPointFileStatus::Pending {
            super::acceptance::preflight(
                s,
                user,
                PowerPointTarget {
                    space_id: space,
                    agent: row.file.agent_instance_id,
                    runtime,
                    capability: "word_template",
                    slot: row.file.slot,
                },
                &capability_preparation::FileChange {
                    file_id: Some(entry.file_id),
                    expected_file_id: row.expected_file_id,
                },
                &json!({}),
                authorization,
            )
            .await?;
        } else if row.file.status != PowerPointFileStatus::Stored
            || !change.expected_file_ids.contains(&entry.file_id)
        {
            return Err(AppError::Conflict(
                "Word template is no longer attached".into(),
            ));
        }
    }
    Ok(draft)
}

pub(crate) async fn attach(
    tx: &mut Transaction<'_, Postgres>,
    user: &CurrentUser,
    space: Uuid,
    agent: Option<(Uuid, i64)>,
    runtime: &str,
    change: &LibraryChange,
) -> AppResult<()> {
    validate(change)?;
    let mut current = own(&mut **tx, space, agent.map(|a| a.0), runtime).await?;
    // Organization replacement may temporarily retain an effective predecessor.
    let mut expected = change.expected_file_ids.clone();
    current.sort();
    expected.sort();
    if current != expected {
        return Err(AppError::Conflict(
            "The Word library changed; reload before saving".into(),
        ));
    }
    let mut slots = std::collections::BTreeSet::new();
    for entry in &change.files {
        let row: FileRow = sqlx::query_as("select * from powerpoint_file where id=$1 for update")
            .bind(entry.file_id)
            .fetch_optional(&mut **tx)
            .await?
            .ok_or(AppError::NotFound)?;
        if row.file.space_id != space
            || row.file.agent_instance_id != agent.map(|a| a.0)
            || row.file.runtime_id.as_deref() != Some(runtime)
            || row.file.capability_id != "word_template"
            || !slots.insert(row.file.slot)
            || (row.file.status != PowerPointFileStatus::Stored
                && (row.file.status != PowerPointFileStatus::Pending
                    || row.actor != user.uid
                    || !row.upload_ready
                    || row.expires_at <= Utc::now()))
        {
            return Err(AppError::Conflict(
                "The staged Word library changed before acceptance".into(),
            ));
        }
    }
    let ids: Vec<_> = change.files.iter().map(|f| f.file_id).collect();
    sqlx::query("update powerpoint_file set status='retired',effective=false,cleanup_due_at=greatest(expires_at,clock_timestamp()) where space_id=$1 and agent_instance_id is not distinct from $2 and runtime_id=$3 and capability_id='word_template' and status='stored' and not(id=any($4)) and ($2::uuid is not null or not effective or not exists(select 1 from powerpoint_file replacement where replacement.id=any($4) and replacement.slot=powerpoint_file.slot))")
        .bind(space).bind(agent.map(|a|a.0)).bind(runtime).bind(&ids).execute(&mut **tx).await?;
    for entry in &change.files {
        sqlx::query("update powerpoint_file set status='stored',published_at=coalesce(published_at,clock_timestamp()),live_agent_id=$2,label=$3 where id=$1")
            .bind(entry.file_id).bind(agent.map(|a|a.0)).bind(entry.label.trim()).execute(&mut **tx).await?;
        let reused=sqlx::query("update capability_preparation set configuration_revision=$2 where file_id=$1 and state in ('ready','pending')")
            .bind(entry.file_id).bind(agent.map(|a|a.1)).execute(&mut **tx).await?.rows_affected()>0;
        if !reused {
            sqlx::query("update capability_preparation set state='obsolete' where file_id=$1 and state<>'obsolete'").bind(entry.file_id).execute(&mut **tx).await?;
            capability_preparation::enqueue(tx, entry.file_id, runtime, agent, &json!({})).await?;
        }
    }
    Ok(())
}

pub(crate) async fn refresh(tx: &mut Transaction<'_, Postgres>, agent: Uuid) -> AppResult<()> {
    // Re-evaluate the aggregate after direct PPT state updates as well.
    sqlx::query("update capability_preparation set configuration_revision=configuration_revision where agent_instance_id=$1 and state<>'obsolete'").bind(agent).execute(&mut **tx).await?;
    Ok(())
}
pub(crate) async fn saved_agent(
    tx: &mut Transaction<'_, Postgres>,
    user: &CurrentUser,
    record: &crate::agent_instances::AgentInstance,
    change: Option<&LibraryChange>,
) -> AppResult<()> {
    if change.is_some_and(|c| !c.files.is_empty()) && !selected(record) {
        return Err(AppError::Unprocessable(
            "Select Word before attaching templates".into(),
        ));
    }
    if let Some(change) = change {
        attach(
            tx,
            user,
            record.space_id,
            Some((record.agent_instance_id, record.configuration_revision)),
            &record.source_runtime_id,
            change,
        )
        .await?;
    }
    if !selected(record) {
        sqlx::query("update capability_preparation set state='obsolete' where agent_instance_id=$1 and capability_id='word_template' and state<>'obsolete'").bind(record.agent_instance_id).execute(&mut **tx).await?;
    } else {
        let rows:Vec<Uuid>=sqlx::query_scalar("select id from powerpoint_file where agent_instance_id=$1 and capability_id='word_template' and status='stored'").bind(record.agent_instance_id).fetch_all(&mut **tx).await?;
        for file in rows {
            let reused=sqlx::query("update capability_preparation set configuration_revision=$2 where file_id=$1 and state in ('ready','pending')").bind(file).bind(record.configuration_revision).execute(&mut **tx).await?.rows_affected()>0;
            if !reused {
                sqlx::query("update capability_preparation set state='obsolete' where file_id=$1 and state<>'obsolete'").bind(file).execute(&mut **tx).await?;
                capability_preparation::enqueue(
                    tx,
                    file,
                    &record.source_runtime_id,
                    Some((record.agent_instance_id, record.configuration_revision)),
                    &json!({}),
                )
                .await?;
            }
        }
    }
    refresh(tx, record.agent_instance_id).await
}

type PreparedEntry = (Uuid, String, String, Option<String>, Option<String>);
pub(crate) async fn bind_result(
    tx: &mut Transaction<'_, Postgres>,
    record: &mut crate::agent_instances::AgentInstance,
    organization: Uuid,
) -> AppResult<()> {
    if !selected(record) {
        return Ok(());
    }
    let entries:Vec<PreparedEntry>=sqlx::query_as("select f.id,f.label,f.sha256,p.state,p.reference from powerpoint_file f left join lateral (select state,reference from capability_preparation where file_id=f.id and state<>'obsolete' order by created_at desc limit 1) p on true where f.runtime_id=$2 and f.capability_id='word_template' and f.status='stored' and (f.agent_instance_id=$1 or (f.agent_instance_id is null and f.space_id=$3 and f.effective and not exists(select 1 from powerpoint_file own where own.agent_instance_id=$1 and own.capability_id='word_template' and own.status='stored'))) order by f.slot")
        .bind(record.agent_instance_id).bind(&record.source_runtime_id).bind(organization).fetch_all(&mut **tx).await?;
    if entries.iter().any(|e| e.3.as_deref() != Some("ready")) {
        return Err(AppError::Conflict(
            "Word templates are still being prepared".into(),
        ));
    }
    let library:Vec<Value>=entries.into_iter().map(|(id,label,sha,_,reference)|json!({"template_key":format!("prepared-{id}.docx"),"label":label,"sha256":sha,"analysis_reference":reference})).collect();
    if let Some(config) = record
        .tuning
        .0
        .pointer_mut("/capability_config/word_template/config")
    {
        *config = json!({"template_library":library});
    }
    Ok(())
}

#[utoipa::path(operation_id="resolve_word_template_library",get,path="/spaces/{space_id}/word-template-library",params(("space_id"=Uuid,Path),("agent_instance_id"=Option<Uuid>,Query),("runtime_id"=Option<String>,Query)),responses((status=200,body=Library)))]
async fn resolve(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<Target>,
) -> AppResult<Json<Library>> {
    let runtime =
        super::http::runtime(&s, space, q.agent_instance_id, q.runtime_id.as_deref()).await?;
    let metadata: Space = crate::db::space(&s.pool, space).await?.into();
    // A draft in a member space may preview only its inherited effective originals.
    let inherited = q.agent_instance_id.is_none() && metadata.kind != SpaceKind::Organization;
    let permission = if q.agent_instance_id.is_none() && !inherited {
        Permission::Manage
    } else {
        Permission::Read
    };
    let owner = authorization::authorize(&s.pool, &user.uid, space, permission).await?;
    if !inherited {
        target(&s.pool, &owner, q.agent_instance_id).await?;
    }
    let files:Vec<LibraryFile>=sqlx::query_as("select distinct on (f.slot) f.*,coalesce(p.state,'failed') preparation_state,p.error preparation_error from powerpoint_file f left join lateral(select state,error from capability_preparation where file_id=f.id and state<>'obsolete' order by created_at desc limit 1) p on true where f.runtime_id=$3 and f.capability_id='word_template' and f.status='stored' and (not $5 or f.effective) and ((f.space_id=$1 and f.agent_instance_id is not distinct from $2) or ($2 is not null and f.space_id=$4 and f.agent_instance_id is null and f.effective and not exists(select 1 from powerpoint_file own where own.agent_instance_id=$2 and own.capability_id='word_template' and own.status='stored'))) order by f.slot,f.effective")
        .bind(if inherited { owner.organization } else { space }).bind(q.agent_instance_id).bind(&runtime).bind(owner.organization).bind(inherited).fetch_all(&s.pool).await?;
    let source = if files.is_empty() {
        PowerPointSource::Builtin
    } else if files[0].file.agent_instance_id.is_some() {
        PowerPointSource::Agent
    } else {
        PowerPointSource::Organization
    };
    let own_file_ids = if inherited {
        vec![]
    } else {
        own(&s.pool, space, q.agent_instance_id, &runtime).await?
    };
    Ok(Json(Library {
        source,
        own_file_ids,
        activation_ready: files.iter().all(|f| f.preparation_state == "ready"),
        files,
    }))
}
#[utoipa::path(operation_id="upload_word_template",put,path="/spaces/{space_id}/word-template-library/uploads",params(("space_id"=Uuid,Path),("agent_instance_id"=Option<Uuid>,Query),("runtime_id"=Option<String>,Query),("template_id"=Option<Uuid>,Query),("expected_file_id"=Option<Uuid>,Query),("slot"=i16,Query),("Idempotency-Key"=Uuid,Header)),request_body(content=crate::documents::http::FileUpload,content_type="multipart/form-data"),responses((status=200,body=PowerPointFile)))]
async fn upload(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<UploadTarget>,
    headers: HeaderMap,
    multipart: Multipart,
) -> AppResult<Json<PowerPointFile>> {
    if !(0..8).contains(&q.slot) {
        return Err(AppError::Unprocessable(
            "Word library slot is outside its bound".into(),
        ));
    }
    let owner = authorization::authorize(
        &s.pool,
        &user.uid,
        space,
        q.agent_instance_id
            .map_or(Permission::Manage, |_| Permission::Write),
    )
    .await?;
    let runtime = if let Some(template) = q.template_id {
        if q.agent_instance_id.is_none()
            || !authorization::can_use_agent(&s.pool, template, &owner).await?
        {
            return Err(AppError::NotFound);
        }
        crate::agents::enrollable_template(&s.pool, &s.agent_catalog, owner.organization, template)
            .await?
            .0
            .source_runtime_id
    } else {
        super::http::runtime(&s, space, q.agent_instance_id, q.runtime_id.as_deref()).await?
    };
    if !s
        .agent_catalog
        .capability_preparation
        .workers
        .contains_key(&runtime)
    {
        return Err(AppError::Unavailable(
            "No preparation worker is configured for this logical pod".into(),
        ));
    }
    if !crate::agents::enablement::usable_capability_ids(&s.pool, &owner, &runtime)
        .await?
        .contains("word_template")
    {
        return Err(AppError::Forbidden);
    }
    Ok(Json(
        super::http::storage(&s)?
            .upload_powerpoint(
                &user,
                PowerPointTarget {
                    space_id: space,
                    agent: q.agent_instance_id,
                    runtime: &runtime,
                    capability: "word_template",
                    slot: q.slot,
                },
                idempotency_key(&headers)?,
                PowerPointChange {
                    expected_file_id: q.expected_file_id,
                },
                PowerPointUpload::Multipart(multipart),
                q.template_id.is_some(),
            )
            .await?,
    ))
}
#[utoipa::path(operation_id="save_word_template_library",put,path="/spaces/{space_id}/word-template-library",params(("space_id"=Uuid,Path),("runtime_id"=Option<String>,Query)),request_body=LibraryChange,responses((status=204)))]
async fn save(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<Target>,
    headers: HeaderMap,
    ApiJson(change): ApiJson<LibraryChange>,
) -> AppResult<StatusCode> {
    if q.agent_instance_id.is_some() {
        return Err(AppError::Unprocessable(
            "Save an agent library with its configuration".into(),
        ));
    }
    let runtime = super::http::runtime(&s, space, None, q.runtime_id.as_deref()).await?;
    let owner = authorization::authorize(&s.pool, &user.uid, space, Permission::Manage).await?;
    target(&s.pool, &owner, None).await?;
    if !crate::agents::enablement::usable_capability_ids(&s.pool, &owner, &runtime)
        .await?
        .contains("word_template")
    {
        return Err(AppError::Forbidden);
    }
    preflight(
        &s,
        &user,
        space,
        None,
        &runtime,
        &change,
        headers.get(axum::http::header::AUTHORIZATION),
    )
    .await?;
    let (mut tx, _) = writer(&s.pool, &user, space, None).await?;
    attach(&mut tx, &user, space, None, &runtime, &change).await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}
pub(crate) fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(resolve, save))
        .routes(routes!(upload).layer(DefaultBodyLimit::max(
            super::super::config::MAX_FILE_BYTES as usize + 64 * 1024,
        )))
}
