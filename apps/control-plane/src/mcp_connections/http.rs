// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::{Connection, McpConfiguration, McpTool, discovery, store};
use crate::{
    api::AppState,
    authorization,
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath},
    onboarding::AdmittedUser,
};
use axum::{Json, extract::State, http::StatusCode};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use utoipa_axum::{router::OpenApiRouter, routes};
use uuid::Uuid;

pub(crate) fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(mcp_connections, create_mcp_connection))
        .routes(routes!(update_mcp_connection))
        .routes(routes!(test_mcp_connection))
        .routes(routes!(publish_mcp_connection))
        .routes(routes!(mcp_credentials))
}

async fn require_admin(s: &AppState, uid: &str) -> AppResult<()> {
    if authorization::is_platform_admin(&s.pool, uid).await? {
        Ok(())
    } else {
        Err(AppError::Forbidden)
    }
}

#[derive(Serialize, ToSchema)]
pub struct McpConnectionView {
    pub id: Uuid,
    pub logical_name: String,
    pub display_name: String,
    pub description: String,
    pub revision: i64,
    pub configuration: McpConfiguration,
    pub enabled: bool,
    pub available: bool,
    pub observation_revision: Option<i64>,
    pub observation_state: String,
    pub error_code: Option<String>,
    pub checked_at: Option<chrono::DateTime<chrono::Utc>>,
    pub last_success_at: Option<chrono::DateTime<chrono::Utc>>,
    pub observed_tools: Vec<McpTool>,
    pub published_tools: Vec<McpTool>,
    pub published_revision: Option<i64>,
    /// Aggregate technical impact only; platform authority grants no business visibility.
    pub affected_instance_count: i64,
}

async fn view(s: &AppState, c: Connection) -> AppResult<McpConnectionView> {
    let affected_instance_count = sqlx::query_scalar(
        "select count(*) from agent_instance where tuning -> 'selected_capability_ids' ? $1",
    )
    .bind(c.capability_id())
    .fetch_one(&s.pool)
    .await?;
    Ok(McpConnectionView {
        available: c.available(),
        id: c.id,
        logical_name: c.logical_name,
        display_name: c.display_name,
        description: c.description,
        revision: c.revision,
        configuration: c.configuration.0,
        enabled: c.enabled,
        observation_revision: c.observation_revision,
        observation_state: c.observation_state,
        error_code: c.error_code,
        checked_at: c.checked_at,
        last_success_at: c.last_success_at,
        observed_tools: c.observed_tools.0,
        published_tools: c.published_tools.0,
        published_revision: c.published_revision,
        affected_instance_count,
    })
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CreateMcpConnection {
    pub logical_name: String,
    pub display_name: String,
    pub description: String,
    pub configuration: McpConfiguration,
}
#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UpdateMcpConnection {
    pub expected_revision: i64,
    pub display_name: String,
    pub description: String,
    pub configuration: McpConfiguration,
    pub enabled: bool,
}
#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct McpRevision {
    pub expected_revision: i64,
}
#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct McpPublication {
    pub expected_revision: i64,
    pub expected_checked_at: chrono::DateTime<chrono::Utc>,
}

fn resolve_configuration(s: &AppState, config: &mut McpConfiguration) -> AppResult<()> {
    if config.is_tabular() && config.url.is_empty() {
        config.url = super::tabular_endpoint(s.agent_catalog.knowledge_flow_url.as_deref())
            .map_err(|_| {
                AppError::Unprocessable("Knowledge Flow service is not configured.".into())
            })?;
        config.allow_insecure_http = config.url.starts_with("http://");
    }
    Ok(())
}

fn validate(
    s: &AppState,
    name: &str,
    description: &str,
    config: &McpConfiguration,
) -> AppResult<()> {
    validate_metadata(name, description)?;
    if config.validate(&s.agent_catalog.mcp_credentials).is_err()
        || config
            .trusted_destination(s.agent_catalog.knowledge_flow_url.as_deref())
            .is_err()
        || (config.is_tabular() && s.directory.is_none())
    {
        return Err(AppError::Unprocessable(
            "Invalid MCP configuration or credential destination.".into(),
        ));
    }
    Ok(())
}
fn validate_metadata(name: &str, description: &str) -> AppResult<()> {
    if name.trim().is_empty() || name.chars().count() > 255 || description.chars().count() > 2000 {
        return Err(AppError::Unprocessable(
            "Invalid MCP name or description.".into(),
        ));
    }
    Ok(())
}
fn audit(actor: &str, c: &Connection, operation: &'static str) {
    tracing::info!(target: fred_rust_sdk::logging::AUDIT_TARGET, actor, operation,
        connection_id = %c.id, revision = c.revision, enabled = c.enabled,
        observation_state = %c.observation_state, "managed MCP connection");
}
async fn require_unique_service(
    conn: &mut sqlx::PgConnection,
    id: Uuid,
    config: &McpConfiguration,
) -> AppResult<()> {
    if config.is_tabular() && sqlx::query_scalar::<_, bool>(
        "select exists(select 1 from mcp_connection where id <> $1 and configuration #>> '{authentication,kind}' = 'knowledge_flow_tabular')"
    ).bind(id).fetch_one(conn).await? {
        return Err(AppError::Conflict("Knowledge Flow Tabular already has a central connection.".into()));
    }
    Ok(())
}

fn conflict() -> AppError {
    AppError::Conflict("MCP connection changed; refresh before continuing.".into())
}

#[utoipa::path(get, path="/platform/mcp-connections", responses((status=200, body=[McpConnectionView]), (status=401, body=crate::error::ErrorBody), (status=403, body=crate::error::ErrorBody)))]
async fn mcp_connections(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
) -> AppResult<Json<Vec<McpConnectionView>>> {
    require_admin(&s, &user.uid).await?;
    let mut result = Vec::new();
    for c in store::list(&s.pool).await? {
        result.push(view(&s, c).await?);
    }
    Ok(Json(result))
}
#[derive(Serialize, ToSchema)]
pub struct McpCredentialReference {
    pub credential_binding: String,
    pub url: String,
    pub available: bool,
}
#[utoipa::path(get, path="/platform/mcp-credentials", responses((status=200, body=[McpCredentialReference]), (status=401, body=crate::error::ErrorBody), (status=403, body=crate::error::ErrorBody)))]
async fn mcp_credentials(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
) -> AppResult<Json<Vec<McpCredentialReference>>> {
    require_admin(&s, &user.uid).await?;
    Ok(Json(
        s.agent_catalog
            .mcp_credentials
            .iter()
            .map(|b| McpCredentialReference {
                credential_binding: b.credential_binding.clone(),
                url: b.url.clone(),
                available: std::env::var(&b.secret_env).is_ok_and(|v| !v.is_empty()),
            })
            .collect(),
    ))
}

#[utoipa::path(post, path="/platform/mcp-connections", request_body=CreateMcpConnection, responses((status=201, body=McpConnectionView), (status=401, body=crate::error::ErrorBody), (status=403, body=crate::error::ErrorBody), (status=409, body=crate::error::ErrorBody), (status=422, body=crate::error::ErrorBody)))]
async fn create_mcp_connection(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiJson(mut body): ApiJson<CreateMcpConnection>,
) -> AppResult<(StatusCode, Json<McpConnectionView>)> {
    require_admin(&s, &user.uid).await?;
    resolve_configuration(&s, &mut body.configuration)?;
    validate(
        &s,
        &body.display_name,
        &body.description,
        &body.configuration,
    )?;
    if !crate::domain::valid_logical_name(&body.logical_name) {
        return Err(AppError::Unprocessable("Invalid logical name.".into()));
    }
    let id = Uuid::new_v4();
    let mut tx = crate::bootstrap::locked(&s.pool).await?;
    authorization::require_platform(
        &mut *tx,
        &user.uid,
        crate::roles::PlatformPermission::ManagePlatform,
    )
    .await?;
    let count: i64 = sqlx::query_scalar("select count(*) from mcp_connection")
        .fetch_one(&mut *tx)
        .await?;
    if count >= 64 {
        return Err(AppError::Conflict("MCP connection limit reached.".into()));
    }
    require_unique_service(&mut tx, id, &body.configuration).await?;
    let inserted=sqlx::query("insert into mcp_connection(id,logical_name,display_name,description,configuration,updated_by) values($1,$2,$3,$4,$5,$6) on conflict(logical_name) do nothing")
        .bind(id).bind(body.logical_name).bind(body.display_name.trim()).bind(body.description)
        .bind(sqlx::types::Json(body.configuration)).bind(&user.uid).execute(&mut *tx).await?;
    if inserted.rows_affected() != 1 {
        return Err(AppError::Conflict(
            "MCP logical name already exists.".into(),
        ));
    }
    let c = store::get(&mut *tx, id).await?;
    store::update_offer(&mut tx, &c).await?;
    tx.commit().await?;
    audit(&user.uid, &c, "created");
    Ok((StatusCode::CREATED, Json(view(&s, c).await?)))
}

#[utoipa::path(put, path="/platform/mcp-connections/{id}", params(("id"=Uuid,Path)), request_body=UpdateMcpConnection, responses((status=200, body=McpConnectionView), (status=401, body=crate::error::ErrorBody), (status=403, body=crate::error::ErrorBody), (status=409, body=crate::error::ErrorBody), (status=422, body=crate::error::ErrorBody)))]
async fn update_mcp_connection(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    ApiJson(mut body): ApiJson<UpdateMcpConnection>,
) -> AppResult<Json<McpConnectionView>> {
    require_admin(&s, &user.uid).await?;
    let mut tx = crate::bootstrap::locked(&s.pool).await?;
    authorization::require_platform(
        &mut *tx,
        &user.uid,
        crate::roles::PlatformPermission::ManagePlatform,
    )
    .await?;
    let current = store::get(&mut *tx, id).await?;
    if current.revision != body.expected_revision {
        return Err(conflict());
    }
    resolve_configuration(&s, &mut body.configuration)?;
    // Withdrawal must remain possible after provisioning changes. It cannot change
    // the technical configuration or bypass the normal checks for activation.
    if !body.enabled && body.configuration == current.configuration.0 {
        validate_metadata(&body.display_name, &body.description)?;
    } else {
        validate(
            &s,
            &body.display_name,
            &body.description,
            &body.configuration,
        )?;
    }
    require_unique_service(&mut tx, id, &body.configuration).await?;
    // A metadata/activation edit preserves a successful technical observation.
    // A destination/authentication edit requires testing and explicit publication again.
    let changed=sqlx::query("update mcp_connection set display_name=$3,description=$4,
        observation_revision=case when configuration=$5 and observation_revision=revision then revision+1 else observation_revision end,
        published_revision=case when configuration=$5 and published_revision=revision then revision+1 else published_revision end,
        observation_state=case when configuration=$5 then observation_state else 'not_observed' end,
        error_code=case when configuration=$5 then error_code else null end,
        configuration=$5,enabled=$6,revision=revision+1,refresh_token=null,updated_by=$7,updated_at=clock_timestamp()
        where id=$1 and revision=$2")
        .bind(id).bind(body.expected_revision).bind(body.display_name.trim()).bind(body.description)
        .bind(sqlx::types::Json(body.configuration)).bind(body.enabled).bind(&user.uid).execute(&mut *tx).await?;
    if changed.rows_affected() != 1 {
        return Err(conflict());
    }
    let c = store::get(&mut *tx, id).await?;
    store::update_offer(&mut tx, &c).await?;
    tx.commit().await?;
    audit(&user.uid, &c, "updated");
    Ok(Json(view(&s, c).await?))
}

#[utoipa::path(post, path="/platform/mcp-connections/{id}/test", params(("id"=Uuid,Path)), request_body=McpRevision, responses((status=200, body=McpConnectionView), (status=401, body=crate::error::ErrorBody), (status=403, body=crate::error::ErrorBody), (status=409, body=crate::error::ErrorBody)))]
async fn test_mcp_connection(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    ApiJson(body): ApiJson<McpRevision>,
) -> AppResult<Json<McpConnectionView>> {
    require_admin(&s, &user.uid).await?;
    let token = Uuid::new_v4();
    let mut claim = crate::bootstrap::locked(&s.pool).await?;
    authorization::require_platform(
        &mut *claim,
        &user.uid,
        crate::roles::PlatformPermission::ManagePlatform,
    )
    .await?;
    let c: Connection = sqlx::query_as(
        "update mcp_connection set refresh_token=$3 where id=$1 and revision=$2 returning *",
    )
    .bind(id)
    .bind(body.expected_revision)
    .bind(token)
    .fetch_optional(&mut *claim)
    .await?
    .ok_or_else(conflict)?;
    claim.commit().await?;
    // No SQL transaction, connection or durable lock during MCP negotiation/listing.
    let observation = discovery::discover(
        &c.configuration,
        &s.agent_catalog.mcp_credentials,
        s.agent_catalog.knowledge_flow_url.as_deref(),
        s.directory.as_ref(),
    )
    .await;
    require_admin(&s, &user.uid).await?;
    let mut tx = crate::bootstrap::locked(&s.pool).await?;
    authorization::require_platform(
        &mut *tx,
        &user.uid,
        crate::roles::PlatformPermission::ManagePlatform,
    )
    .await?;
    let (state, error, tools) = match observation {
        Ok(tools) => ("available", None, Some(sqlx::types::Json(tools))),
        Err(code) => ("unavailable", Some(code), None),
    };
    let c:Connection=sqlx::query_as("update mcp_connection set observation_state=$4,error_code=$5,
        observed_tools=coalesce($6,observed_tools),observation_revision=revision,checked_at=clock_timestamp(),
        last_success_at=case when $4='available' then clock_timestamp() else last_success_at end,refresh_token=null
        where id=$1 and revision=$2 and refresh_token=$3 returning *")
        .bind(id).bind(body.expected_revision).bind(token).bind(state).bind(error).bind(tools)
        .fetch_optional(&mut *tx).await?.ok_or_else(conflict)?;
    store::update_offer(&mut tx, &c).await?;
    tx.commit().await?;
    audit(&user.uid, &c, "observed");
    Ok(Json(view(&s, c).await?))
}

#[utoipa::path(post, path="/platform/mcp-connections/{id}/publish", params(("id"=Uuid,Path)), request_body=McpPublication, responses((status=200, body=McpConnectionView), (status=401, body=crate::error::ErrorBody), (status=403, body=crate::error::ErrorBody), (status=409, body=crate::error::ErrorBody)))]
async fn publish_mcp_connection(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    ApiJson(body): ApiJson<McpPublication>,
) -> AppResult<Json<McpConnectionView>> {
    require_admin(&s, &user.uid).await?;
    let mut tx = crate::bootstrap::locked(&s.pool).await?;
    authorization::require_platform(
        &mut *tx,
        &user.uid,
        crate::roles::PlatformPermission::ManagePlatform,
    )
    .await?;
    let c:Connection=sqlx::query_as("update mcp_connection set published_tools=observed_tools,published_revision=revision+1,
        observation_revision=revision+1,revision=revision+1,refresh_token=null,updated_by=$3,updated_at=clock_timestamp()
        where id=$1 and revision=$2 and observation_revision=revision and observation_state='available'
        and jsonb_array_length(observed_tools)>0 and checked_at=$4 returning *")
        .bind(id).bind(body.expected_revision).bind(&user.uid).bind(body.expected_checked_at).fetch_optional(&mut *tx).await?.ok_or_else(conflict)?;
    store::update_offer(&mut tx, &c).await?;
    tx.commit().await?;
    audit(&user.uid, &c, "published");
    Ok(Json(view(&s, c).await?))
}
