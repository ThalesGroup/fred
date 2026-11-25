// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;
use crate::{
    authorization::{self, RuntimeCaller},
    domain::Permission,
    extract::{ApiJson, ApiPath, ApiQuery},
    onboarding::AdmittedUser,
};
use axum::{Json as ResponseJson, extract::State, http::StatusCode};
use utoipa_axum::{router::OpenApiRouter, routes};

#[derive(Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct Definition {
    pub id: String,
    pub version: String,
    pub name: String,
    pub description: String,
    #[serde(default = "default_icon")]
    pub icon: String,
    pub config_schema: Value,
}
fn default_icon() -> String {
    "folder".into()
}
#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PublishDefinitions {
    pub runtime_id: String,
    pub definitions: Vec<Definition>,
}
#[utoipa::path(post,path="/knowledge-base-definitions/publish",request_body=PublishDefinitions,responses((status=204),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody)))]
async fn publish(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiJson(input): ApiJson<PublishDefinitions>,
) -> AppResult<StatusCode> {
    worker(&s, &user, &input.runtime_id)?;
    if input.definitions.len() > 64 {
        return Err(AppError::Unprocessable("Too many definitions.".into()));
    }
    let mut ids = std::collections::HashSet::new();
    for d in &input.definitions {
        if !d
            .id
            .as_bytes()
            .first()
            .is_some_and(u8::is_ascii_alphanumeric)
            || d.id.len() > 128
            || !d.id.bytes().all(|c| {
                c.is_ascii_lowercase() || c.is_ascii_digit() || matches!(c, b'.' | b'_' | b'-')
            })
            || !ids.insert(&d.id)
            || crate::domain::canonical_name(&d.name, 255).as_deref() != Some(&d.name)
            || crate::domain::canonical_name(&d.version, 64).as_deref() != Some(&d.version)
            || crate::domain::canonical_name(&d.icon, 128).as_deref() != Some(&d.icon)
            || d.description.len() > 2000
            || !d.config_schema.is_object()
            || serde_json::to_vec(&d.config_schema)
                .map_err(anyhow::Error::from)?
                .len()
                > 65536
        {
            return Err(AppError::Unprocessable(
                "Invalid knowledge base definition.".into(),
            ));
        }
        super::configuration::fields(&d.config_schema)?;
    }
    let mut tx = s.pool.begin().await?;
    sqlx::query("insert into runtime_catalog(runtime_id,reachable,observed_at) values($1,true,clock_timestamp()) on conflict(runtime_id) do update set reachable=true,checked_at=clock_timestamp(),observed_at=clock_timestamp()")
        .bind(&input.runtime_id).execute(&mut *tx).await?;
    for d in &input.definitions {
        let owner: Option<String> =
            sqlx::query_scalar("select runtime_id from kb_definition where id=$1")
                .bind(&d.id)
                .fetch_optional(&mut *tx)
                .await?;
        if owner.as_ref().is_some_and(|o| o != &input.runtime_id) {
            return Err(AppError::Conflict(
                "Definition belongs to another runtime.".into(),
            ));
        }
        let capability = format!("knowledge-base:{}", d.id);
        let descriptor = serde_json::json!({"id":capability,"version":d.version,"name":d.name,"description":d.description,"icon":d.icon,"kind":"knowledge_base","execution_models":[]});
        sqlx::query("insert into capability_offer(source_id,capability_id,version,descriptor,advertised) values($1,$2,$3,$4,true) on conflict(source_id,capability_id) do update set version=excluded.version,descriptor=excluded.descriptor,advertised=true")
            .bind(&input.runtime_id).bind(&capability).bind(&d.version).bind(descriptor).execute(&mut *tx).await?;
        let changed = sqlx::query("insert into kb_definition(id,runtime_id,config_schema) values($1,$2,$3) on conflict(id) do update set config_schema=excluded.config_schema where kb_definition.runtime_id=excluded.runtime_id")
            .bind(&d.id).bind(&input.runtime_id).bind(&d.config_schema).execute(&mut *tx).await?.rows_affected();
        if changed != 1 {
            return Err(AppError::Conflict(
                "Definition belongs to another runtime.".into(),
            ));
        }
    }
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

#[derive(Serialize, ToSchema)]
#[schema(as=AvailableKnowledgeBaseDefinition)]
pub struct AvailableDefinition {
    pub runtime_id: String,
    pub definition: Definition,
    pub credential_bindings: Vec<String>,
}
#[utoipa::path(get,path="/spaces/{space_id}/knowledge-base-definitions",params(("space_id"=Uuid,Path)),responses((status=422,body=crate::error::ErrorBody),(status=200,body=[AvailableDefinition]),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody)))]
async fn definitions(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space_id): ApiPath<Uuid>,
) -> AppResult<ResponseJson<Vec<AvailableDefinition>>> {
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let space = authorization::authorize(&mut *tx, &user.uid, space_id, Permission::Manage).await?;
    let policy = crate::agents::enablement::Policy::load_for_space(&mut *tx, &space).await?;
    let rows:Vec<(String,String,Json<Value>,Json<Value>)>=sqlx::query_as("select d.id,d.runtime_id,d.config_schema,o.descriptor from kb_definition d join capability_offer o on o.source_id=d.runtime_id and o.capability_id=d.capability_id where o.advertised order by d.id limit 200").fetch_all(&mut *tx).await?;
    let mut result = Vec::new();
    for (id, runtime, schema, descriptor) in rows {
        if !s
            .agent_catalog
            .knowledge_bases
            .workers
            .contains_key(&runtime)
            || !crate::agents::enablement::usable(
                &policy,
                &space,
                &runtime,
                &format!("knowledge-base:{id}"),
            )
        {
            continue;
        }
        let text = |key: &str| {
            descriptor
                .0
                .get(key)
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_owned()
        };
        result.push(AvailableDefinition {
            credential_bindings: s
                .agent_catalog
                .knowledge_bases
                .credentials
                .iter()
                .filter(|b| b.space_id == space_id && b.runtime_id == runtime)
                .map(|b| b.credential_binding.clone())
                .collect(),
            runtime_id: runtime,
            definition: Definition {
                id,
                version: text("version"),
                name: text("name"),
                description: text("description"),
                icon: text("icon"),
                config_schema: schema.0,
            },
        });
    }
    tx.commit().await?;
    Ok(ResponseJson(result))
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
#[schema(as=KnowledgeBaseInstance)]
pub struct Instance {
    pub id: Uuid,
    pub definition_id: String,
    pub space_id: Uuid,
    pub folder_id: Uuid,
    #[schema(value_type=Object)]
    pub config: Json<Value>,
    #[schema(value_type=Object)]
    pub credential_refs: Json<Value>,
    pub profile: String,
    pub paused: bool,
    pub interval_seconds: Option<i32>,
}
const INSTANCE_SELECT: &str = "select id,definition_id,space_id,folder_id,config,credential_refs,profile,paused,interval_seconds from kb_instance";
async fn instance(conn: &mut PgConnection, id: Uuid) -> AppResult<Instance> {
    sqlx::query_as(sqlx::AssertSqlSafe(format!(
        "{INSTANCE_SELECT} where id=$1"
    )))
    .bind(id)
    .fetch_optional(conn)
    .await?
    .ok_or(AppError::NotFound)
}
#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CreateInstance {
    pub definition_id: String,
    pub name: String,
    pub config: Value,
    #[serde(default)]
    pub credential_refs: std::collections::BTreeMap<String, String>,
    pub profile: String,
    pub interval_seconds: Option<i32>,
}
fn interval(value: Option<i32>) -> AppResult<()> {
    if value.is_some_and(|v| !(60..=31536000).contains(&v)) {
        return Err(AppError::Unprocessable(
            "Invalid synchronization interval.".into(),
        ));
    }
    Ok(())
}
#[utoipa::path(get,path="/spaces/{space_id}/knowledge-bases",params(("space_id"=Uuid,Path)),responses((status=422,body=crate::error::ErrorBody),(status=200,body=[Instance]),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody)))]
async fn list(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space): ApiPath<Uuid>,
) -> AppResult<ResponseJson<Vec<Instance>>> {
    let mut conn = s.pool.acquire().await?;
    authorization::authorize(&mut *conn, &user.uid, space, Permission::Manage).await?;
    Ok(ResponseJson(
        sqlx::query_as(sqlx::AssertSqlSafe(format!(
            "{INSTANCE_SELECT} where space_id=$1 order by id limit 200"
        )))
        .bind(space)
        .fetch_all(&mut *conn)
        .await?,
    ))
}
#[utoipa::path(post,path="/spaces/{space_id}/knowledge-bases",params(("space_id"=Uuid,Path)),request_body=CreateInstance,responses((status=201,body=Instance),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn create(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space_id): ApiPath<Uuid>,
    ApiJson(input): ApiJson<CreateInstance>,
) -> AppResult<(StatusCode, ResponseJson<Instance>)> {
    interval(input.interval_seconds)?;
    if crate::domain::canonical_name(&input.name, 255).as_deref() != Some(&input.name)
        || !input.config.is_object()
        || serde_json::to_vec(&input.config)
            .map_err(anyhow::Error::from)?
            .len()
            > 65536
        || input
            .config
            .get("profile")
            .is_some_and(|v| v.as_str() != Some(&input.profile))
        || !matches!(input.profile.as_str(), "fast" | "medium" | "rich")
    {
        return Err(AppError::Unprocessable(
            "Invalid knowledge base instance.".into(),
        ));
    }
    let (mut tx, space) =
        crate::spaces::authorized_mutation(&s.pool, &user.uid, space_id, Permission::Manage)
            .await?;
    let (runtime, schema): (String, Json<Value>) =
        sqlx::query_as("select runtime_id,config_schema from kb_definition where id=$1 for share")
            .bind(&input.definition_id)
            .fetch_optional(&mut *tx)
            .await?
            .ok_or(AppError::NotFound)?;
    let fields = super::configuration::fields(&schema.0)?;
    let config = super::configuration::normalize(
        &fields,
        &input.config,
        &input.credential_refs,
        &input.profile,
    )?;
    for reference in input.credential_refs.values() {
        if !s
            .agent_catalog
            .knowledge_bases
            .credentials
            .iter()
            .any(|binding| {
                binding.runtime_id == runtime
                    && binding.space_id == space_id
                    && binding.credential_binding == *reference
            })
        {
            return Err(AppError::Forbidden);
        }
    }
    let policy = crate::agents::enablement::Policy::load_for_space(&mut *tx, &space).await?;
    let available: bool = sqlx::query_scalar(
        "select advertised from capability_offer where source_id=$1 and capability_id=$2 for share",
    )
    .bind(&runtime)
    .bind(format!("knowledge-base:{}", input.definition_id))
    .fetch_one(&mut *tx)
    .await?;
    if !available
        || !s
            .agent_catalog
            .knowledge_bases
            .workers
            .contains_key(&runtime)
        || s.agent_catalog
            .runtime_catalog_sources
            .iter()
            .any(|r| r.runtime_id == runtime && !r.enabled)
        || !crate::agents::enablement::usable(
            &policy,
            &space,
            &runtime,
            &format!("knowledge-base:{}", input.definition_id),
        )
    {
        return Err(AppError::Forbidden);
    }
    if s.processing.is_none() {
        return Err(crate::processing::unavailable());
    }
    let folder = Uuid::new_v4();
    let id = Uuid::new_v4();
    sqlx::query("insert into folder(id,space_id,name,path) values($1,$2,$3,$4)")
        .bind(folder)
        .bind(space_id)
        .bind(input.name)
        .bind(format!("/{folder}/"))
        .execute(&mut *tx)
        .await?;
    sqlx::query("insert into kb_instance(id,definition_id,space_id,folder_id,config,credential_refs,profile,interval_seconds,next_run_at,created_by) values($1,$2,$3,$4,$5,$6,$7,$8,case when $8::integer is null then null else clock_timestamp() end,$9)").bind(id).bind(input.definition_id).bind(space_id).bind(folder).bind(config).bind(serde_json::to_value(input.credential_refs).map_err(anyhow::Error::from)?).bind(input.profile).bind(input.interval_seconds).bind(&user.uid).execute(&mut *tx).await?;
    let result = instance(&mut tx, id).await?;
    tx.commit().await?;
    Ok((StatusCode::CREATED, ResponseJson(result)))
}
#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UpdateInstance {
    pub paused: bool,
    pub interval_seconds: Option<i32>,
}
#[utoipa::path(patch,path="/knowledge-bases/{id}",params(("id"=Uuid,Path)),request_body=UpdateInstance,responses((status=200,body=Instance),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody)))]
async fn update(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    ApiJson(input): ApiJson<UpdateInstance>,
) -> AppResult<ResponseJson<Instance>> {
    interval(input.interval_seconds)?;
    let row = instance(&mut *s.pool.acquire().await?, id).await?;
    let (mut tx, _) =
        crate::spaces::authorized_mutation(&s.pool, &user.uid, row.space_id, Permission::Manage)
            .await?;
    sqlx::query("update kb_instance set paused=$2,interval_seconds=$3,next_run_at=case when $2 or $3::integer is null then null else clock_timestamp()+make_interval(secs=>$3) end where id=$1").bind(id).bind(input.paused).bind(input.interval_seconds).execute(&mut *tx).await?;
    let result = instance(&mut tx, id).await?;
    tx.commit().await?;
    Ok(ResponseJson(result))
}
#[utoipa::path(get,path="/knowledge-bases/{id}/runs",params(("id"=Uuid,Path)),responses((status=422,body=crate::error::ErrorBody),(status=200,body=[Run]),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody)))]
async fn knowledge_base_runs(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<ResponseJson<Vec<Run>>> {
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let row = instance(&mut tx, id).await?;
    authorization::authorize(&mut *tx, &user.uid, row.space_id, Permission::Manage).await?;
    let rows = sqlx::query_as(sqlx::AssertSqlSafe(format!(
        "{RUN_SELECT} where instance_id=$1 order by created_at desc,id desc limit 50"
    )))
    .bind(id)
    .fetch_all(&mut *tx)
    .await?;
    tx.commit().await?;
    Ok(ResponseJson(rows))
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct StartRun {
    pub request_key: String,
}
#[utoipa::path(post,path="/knowledge-bases/{id}/runs",params(("id"=Uuid,Path)),request_body=StartRun,responses((status=202,body=Run),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn start_knowledge_base_run(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    ApiJson(input): ApiJson<StartRun>,
) -> AppResult<(StatusCode, ResponseJson<Run>)> {
    if input.request_key.is_empty()
        || input.request_key.len() > 128
        || input.request_key.chars().any(char::is_control)
    {
        return Err(AppError::Unprocessable("Invalid request key.".into()));
    }
    let row = instance(&mut *s.pool.acquire().await?, id).await?;
    let (mut tx, _) =
        crate::spaces::authorized_mutation(&s.pool, &user.uid, row.space_id, Permission::Manage)
            .await?;
    let run = enqueue(&mut tx, &s, id, &input.request_key, &user.uid).await?;
    tx.commit().await?;
    Ok((StatusCode::ACCEPTED, ResponseJson(run)))
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct WorkerTarget {
    runtime_id: String,
    definition_id: String,
}
#[derive(Serialize, ToSchema)]
#[schema(as=KnowledgeBaseWorkerBinding)]
struct WorkerBinding {
    installation_id: Uuid,
    task_queue: String,
}
#[utoipa::path(get,path="/knowledge-bases/worker",params(("runtime_id"=String,Query),("definition_id"=String,Query)),responses((status=422,body=crate::error::ErrorBody),(status=200,body=WorkerBinding),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody)))]
async fn binding(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiQuery(q): ApiQuery<WorkerTarget>,
) -> AppResult<ResponseJson<WorkerBinding>> {
    worker(&s, &user, &q.runtime_id)?;
    let owned: bool = sqlx::query_scalar(
        "select exists(select 1 from kb_definition where id=$1 and runtime_id=$2)",
    )
    .bind(&q.definition_id)
    .bind(&q.runtime_id)
    .fetch_one(&s.pool)
    .await?;
    if !owned {
        return Err(AppError::NotFound);
    }
    let installation_id =
        sqlx::query_scalar("select namespace from document_storage where singleton")
            .fetch_one(&s.pool)
            .await?;
    Ok(ResponseJson(WorkerBinding {
        installation_id,
        task_queue: queue(installation_id, &q.runtime_id, &q.definition_id),
    }))
}
#[utoipa::path(get,path="/knowledge-base-runs/{id}",params(("id"=Uuid,Path)),responses((status=422,body=crate::error::ErrorBody),(status=200,body=Run),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody)))]
async fn context(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<ResponseJson<Run>> {
    Ok(ResponseJson(authorize_run(&s, &user, id).await?))
}
#[utoipa::path(post,path="/knowledge-base-runs/{id}/claim",params(("id"=Uuid,Path)),responses((status=422,body=crate::error::ErrorBody),(status=200,body=Run),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody)))]
async fn claim_knowledge_base_run(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<ResponseJson<Run>> {
    let row = authorize_run(&s, &user, id).await?;
    let mut tx = s.pool.begin().await?;
    let space: crate::domain::Space = crate::db::space(&mut *tx, row.space_id).await?.into();
    crate::spaces::lock_organization(&mut tx, &space).await?;
    // A lost completion response must not execute a terminal scan again.
    let current = run(&mut tx, id).await?;
    if matches!(current.state.as_str(), "succeeded" | "failed") {
        tx.commit().await?;
        return Ok(ResponseJson(current));
    }
    ensure_run_active(&mut tx, id).await?;
    sqlx::query("update kb_run set state='running' where id=$1")
        .bind(id)
        .execute(&mut *tx)
        .await?;
    let result = run(&mut tx, id).await?;
    tx.commit().await?;
    Ok(ResponseJson(result))
}
#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CompleteRun {
    pub error_code: Option<String>,
    pub result: Value,
}
#[utoipa::path(post,path="/knowledge-base-runs/{id}/complete",params(("id"=Uuid,Path)),request_body=CompleteRun,responses((status=204),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody)))]
async fn complete(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath(id): ApiPath<Uuid>,
    ApiJson(input): ApiJson<CompleteRun>,
) -> AppResult<StatusCode> {
    if !input.result.is_object()
        || serde_json::to_vec(&input.result)
            .map_err(anyhow::Error::from)?
            .len()
            > 65536
        || input.error_code.as_ref().is_some_and(|c| {
            c.is_empty()
                || c.len() > 64
                || !c
                    .bytes()
                    .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_')
        })
    {
        return Err(AppError::Unprocessable("Invalid run result.".into()));
    }
    let row = authorize_run(&s, &user, id).await?;
    let mut tx = s.pool.begin().await?;
    let space: crate::domain::Space = crate::db::space(&mut *tx, row.space_id).await?.into();
    crate::spaces::lock_organization(&mut tx, &space).await?;
    let existing: (String, Option<String>, Option<Json<Value>>) =
        sqlx::query_as("select state,error_code,result from kb_run where id=$1 for update")
            .bind(id)
            .fetch_one(&mut *tx)
            .await?;
    if matches!(existing.0.as_str(), "succeeded" | "failed") {
        if existing.1 == input.error_code
            && existing.2.as_ref().map(|v| &v.0) == Some(&input.result)
        {
            return Ok(StatusCode::NO_CONTENT);
        }
        return Err(AppError::Conflict("Run already completed.".into()));
    }
    ensure_run_active(&mut tx, id).await?;
    sqlx::query("update kb_run set state=$2,completed_at=clock_timestamp(),error_code=$3,result=$4 where id=$1").bind(id).bind(if input.error_code.is_some(){"failed"}else{"succeeded"}).bind(input.error_code).bind(input.result).execute(&mut *tx).await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}
pub(crate) fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(publish))
        .routes(routes!(definitions))
        .routes(routes!(list, create))
        .routes(routes!(update))
        .routes(routes!(start_knowledge_base_run, knowledge_base_runs))
        .routes(routes!(binding))
        .routes(routes!(context))
        .routes(routes!(claim_knowledge_base_run))
        .routes(routes!(complete))
        .merge(super::documents::routes())
}
